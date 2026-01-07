import asyncio
import subprocess
from dataclasses import dataclass
from typing import Optional

from utils.logging import get_logger


@dataclass
class ArenaCamConfig:
    mode: str = "rtp_h264"  # "rtp_h264" or "udp_jpeg"
    bind_ip: str = "0.0.0.0"
    bind_port: int = 5000
    rtp_payload: int = 96


class ArenaCamBase:
    def __init__(self):
        self._latest_frame: Optional[bytes] = None

    @property
    def latest_frame(self) -> Optional[bytes]:
        return self._latest_frame

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError


class ArenaCamUDPJPEG(ArenaCamBase):
    """
    Very simple UDP receiver:
      - Assumes each UDP datagram contains one complete JPEG frame.
    """

    def __init__(self, cfg: ArenaCamConfig):
        super().__init__()
        self.cfg = cfg
        self._logger = get_logger("ArenaCamUDPJPEG")
        self._transport: Optional[asyncio.DatagramTransport] = None

    @staticmethod
    def _looks_like_jpeg(data: bytes) -> bool:
        return (
            len(data) >= 4
            and data[0] == 0xFF
            and data[1] == 0xD8
            and data[-2] == 0xFF
            and data[-1] == 0xD9
        )

    async def start(self) -> None:
        if self._transport is not None:
            self._logger.warn("Already started")
            return

        loop = asyncio.get_running_loop()

        def on_datagram(data: bytes, addr):
            if self._looks_like_jpeg(data):
                self._latest_frame = data

        class _Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data: bytes, addr):
                on_datagram(data, addr)

        self._logger.info(f"Starting UDP-JPEG receiver on {self.cfg.bind_ip}:{self.cfg.bind_port}")
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _Proto(),
            local_addr=(self.cfg.bind_ip, self.cfg.bind_port),
        )
        self._transport = transport  # type: ignore[assignment]
        self._logger.info("UDP-JPEG receiver started")

    async def stop(self) -> None:
        if self._transport is None:
            return
        self._transport.close()
        self._transport = None
        self._logger.info("UDP-JPEG receiver stopped")


class ArenaCamRtpH264(ArenaCamBase):
    """
    Receives RTP/H.264 over UDP and decodes into JPEG frames using a GStreamer subprocess.

    Pipeline (conceptually):
      udpsrc ! application/x-rtp(H264) ! rtph264depay ! avdec_h264 ! jpegenc ! fdsink

    Python reads concatenated JPEGs from stdout and extracts frames by SOI/EOI markers.
    """

    def __init__(self, cfg: ArenaCamConfig):
        super().__init__()
        self.cfg = cfg
        self._logger = get_logger("ArenaCamRtpH264")
        self._proc: Optional[subprocess.Popen] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _gst_cmd(self) -> list[str]:
        caps = (
            f"application/x-rtp,media=video,encoding-name=H264,payload={int(self.cfg.rtp_payload)}"
        )

        # Note: bind_ip is not strictly required for udpsrc; port is key.
        # We keep it simple and bind to the port.
        return [
            "gst-launch-1.0",
            "-q",
            "udpsrc",
            f"port={int(self.cfg.bind_port)}",
            f"caps={caps}",
            "!",
            "rtph264depay",
            "!",
            "h264parse",
            "!",
            "avdec_h264",
            "!",
            "videoconvert",
            "!",
            "jpegenc",
            "!",
            "fdsink",
        ]

    @staticmethod
    def _extract_jpegs_from_buffer(buf: bytearray) -> list[bytes]:
        """
        Extract all complete JPEGs from buf, leaving remainder in buf.
        JPEG frame is between SOI (FFD8) and EOI (FFD9), inclusive.
        """
        frames: list[bytes] = []
        while True:
            soi = buf.find(b"\xff\xd8")
            if soi == -1:
                # no start marker; drop old data if buffer is huge
                if len(buf) > 2_000_000:
                    del buf[:-2]
                break

            eoi = buf.find(b"\xff\xd9", soi + 2)
            if eoi == -1:
                # wait for more data
                if soi > 0:
                    del buf[:soi]  # discard leading junk
                break

            frame = bytes(buf[soi : eoi + 2])
            frames.append(frame)
            del buf[: eoi + 2]

        return frames

    async def start(self) -> None:
        if self._running:
            self._logger.warn("Already started")
            return

        cmd = self._gst_cmd()
        self._logger.info("Starting GStreamer decode pipeline for RTP/H264")
        self._logger.info("GStreamer cmd: " + " ".join(cmd))

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except FileNotFoundError:
            self._logger.fatal("gst-launch-1.0 not found. Install GStreamer on the VM.")
            raise

        if self._proc.stdout is None:
            raise RuntimeError("Failed to open stdout from gstreamer process")

        self._running = True
        self._task = asyncio.create_task(self._reader_loop())

        # Also watch stderr to help debugging if pipeline fails
        asyncio.create_task(self._stderr_watcher())

        self._logger.info("ArenaCam RTP/H264 started")

    async def _stderr_watcher(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return

        loop = asyncio.get_running_loop()
        while self._running and self._proc.poll() is None:
            line = await loop.run_in_executor(None, self._proc.stderr.readline)
            if not line:
                await asyncio.sleep(0.05)
                continue
            # Only show in DEBUG unless user raised log level
            self._logger.debug("GST: " + line.decode("utf-8", errors="replace").rstrip())

    async def _reader_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        loop = asyncio.get_running_loop()
        buf = bytearray()
        frames = 0

        while self._running and self._proc.poll() is None:
            chunk = await loop.run_in_executor(None, self._proc.stdout.read, 4096)
            if not chunk:
                await asyncio.sleep(0.001)
                continue

            buf.extend(chunk)
            extracted = self._extract_jpegs_from_buffer(buf)
            for jpg in extracted:
                self._latest_frame = jpg
                frames += 1
                if frames % 60 == 0:
                    self._logger.debug(f"Decoded {frames} JPEG frames")

        self._logger.warn("GStreamer decode loop ended")

    async def stop(self) -> None:
        self._running = False

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except asyncio.TimeoutError:
                pass
            self._task = None

        if self._proc is not None:
            self._logger.info("Stopping GStreamer pipeline")
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None

        self._logger.info("ArenaCam RTP/H264 stopped")


def create_arenacam(cfg: ArenaCamConfig) -> ArenaCamBase:
    mode = (cfg.mode or "").strip().lower()
    if mode == "udp_jpeg":
        return ArenaCamUDPJPEG(cfg)
    # default
    return ArenaCamRtpH264(cfg)
