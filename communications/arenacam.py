import asyncio
import os
import signal
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
    """Very simple UDP receiver; one complete JPEG is expected per datagram."""

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
            self._logger.warning("Already started")
            return

        loop = asyncio.get_running_loop()

        def on_datagram(data: bytes, addr):
            if self._looks_like_jpeg(data):
                self._latest_frame = data

        class _Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data: bytes, addr):
                on_datagram(data, addr)

        self._logger.info(
            f"Starting UDP-JPEG receiver on {self.cfg.bind_ip}:{self.cfg.bind_port}"
        )
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
        # Give asyncio one turn to actually close the underlying socket.
        await asyncio.sleep(0)
        self._logger.info("UDP-JPEG receiver stopped")


class ArenaCamRtpH264(ArenaCamBase):
    """
    Receives RTP/H.264 over UDP and decodes it into JPEG frames with GStreamer.

    GStreamer is placed in its own process group.  On shutdown we terminate the
    entire group, wait for it to exit, and escalate to SIGKILL if necessary.
    This prevents an orphaned gst-launch process from keeping UDP port 5000.
    """

    def __init__(self, cfg: ArenaCamConfig):
        super().__init__()
        self.cfg = cfg
        self._logger = get_logger("ArenaCamRtpH264")
        self._proc: Optional[subprocess.Popen] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._running = False

    def _gst_cmd(self) -> list[str]:
        caps = (
            f"application/x-rtp,media=video,encoding-name=H264,payload={int(self.cfg.rtp_payload)}"
        )
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
        frames: list[bytes] = []
        while True:
            soi = buf.find(b"\xff\xd8")
            if soi == -1:
                if len(buf) > 2_000_000:
                    del buf[:-2]
                break

            eoi = buf.find(b"\xff\xd9", soi + 2)
            if eoi == -1:
                if soi > 0:
                    del buf[:soi]
                break

            frames.append(bytes(buf[soi : eoi + 2]))
            del buf[: eoi + 2]

        return frames

    async def start(self) -> None:
        if self._running:
            self._logger.warning("Already started")
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
                start_new_session=True,
            )
        except FileNotFoundError:
            self._logger.fatal("gst-launch-1.0 not found. Install GStreamer on the VM.")
            raise

        if self._proc.stdout is None:
            raise RuntimeError("Failed to open stdout from GStreamer process")

        self._running = True
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._stderr_task = asyncio.create_task(self._stderr_watcher())
        self._logger.info(f"ArenaCam RTP/H264 started (GStreamer PID {self._proc.pid})")

    async def _stderr_watcher(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return

        loop = asyncio.get_running_loop()
        try:
            while self._running and proc.poll() is None:
                line = await loop.run_in_executor(None, proc.stderr.readline)
                if not line:
                    await asyncio.sleep(0.05)
                    continue
                self._logger.debug(
                    "GST: " + line.decode("utf-8", errors="replace").rstrip()
                )
        except asyncio.CancelledError:
            return

    async def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return

        loop = asyncio.get_running_loop()
        buf = bytearray()
        frames = 0

        try:
            while self._running and proc.poll() is None:
                chunk = await loop.run_in_executor(None, proc.stdout.read, 4096)
                if not chunk:
                    await asyncio.sleep(0.001)
                    continue

                buf.extend(chunk)
                for jpg in self._extract_jpegs_from_buffer(buf):
                    self._latest_frame = jpg
                    frames += 1
                    if frames % 60 == 0:
                        self._logger.debug(f"Decoded {frames} JPEG frames")
        except asyncio.CancelledError:
            return
        finally:
            if self._running:
                self._logger.warning("GStreamer decode loop ended unexpectedly")

    def _signal_process_group(self, sig: int) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return

        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
        except Exception as e:
            self._logger.warning(f"Could not signal GStreamer process group: {e}")
            try:
                proc.send_signal(sig)
            except Exception:
                pass

    async def stop(self) -> None:
        self._running = False
        proc = self._proc

        if proc is not None and proc.poll() is None:
            self._logger.info(f"Stopping GStreamer process group (PID {proc.pid})")
            self._signal_process_group(signal.SIGTERM)

            try:
                await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=1.5)
            except asyncio.TimeoutError:
                self._logger.warning("GStreamer did not exit after SIGTERM; sending SIGKILL")
                self._signal_process_group(signal.SIGKILL)
                try:
                    await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=1.0)
                except asyncio.TimeoutError:
                    self._logger.error("GStreamer still did not exit after SIGKILL")

        # Closing the pipes releases any executor threads blocked in read/readline.
        if proc is not None:
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    try:
                        pipe.close()
                    except Exception:
                        pass

        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()

        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                try:
                    await asyncio.wait_for(task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass

        self._reader_task = None
        self._stderr_task = None
        self._proc = None
        self._latest_frame = None
        self._logger.info("ArenaCam RTP/H264 stopped")


def create_arenacam(cfg: ArenaCamConfig) -> ArenaCamBase:
    mode = (cfg.mode or "").strip().lower()
    if mode == "udp_jpeg":
        return ArenaCamUDPJPEG(cfg)
    return ArenaCamRtpH264(cfg)
