import asyncio
from dataclasses import dataclass
from typing import Optional

from utils.logging import get_logger


@dataclass
class ArenaCamConfig:
    bind_ip: str = "0.0.0.0"
    bind_port: int = 5000


class _UDPJPEGProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_frame, logger):
        self._on_frame = on_frame
        self._logger = logger

    def datagram_received(self, data: bytes, addr):
        if len(data) < 4:
            return
        self._on_frame(data)


class ArenaCamUDP:
    def __init__(self, cfg: ArenaCamConfig):
        self.cfg = cfg
        self._logger = get_logger("ArenaCamUDP")
        self._transport = None
        self._latest_frame: Optional[bytes] = None

    @property
    def latest_frame(self) -> Optional[bytes]:
        return self._latest_frame

    async def start(self):
        if self._transport:
            return

        loop = asyncio.get_running_loop()

        def on_frame(data: bytes):
            self._latest_frame = data

        self._logger.info(
            f"Starting UDP camera on {self.cfg.bind_ip}:{self.cfg.bind_port}"
        )

        transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPJPEGProtocol(on_frame, self._logger),
            local_addr=(self.cfg.bind_ip, self.cfg.bind_port),
        )

        self._transport = transport
        self._logger.info("UDP camera started")

    async def stop(self):
        if self._transport:
            self._transport.close()
            self._transport = None
            self._logger.info("UDP camera stopped")
