import asyncio
import json
import logging
import socket
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from aiohttp import web

from utils.logging import get_logger, parse_level
from utils.port_guard import ensure_ports_available
from communications.arenacam import ArenaCamConfig, create_arenacam
from vision.arena import ArenaConfig, ArenaProcessor
from frontend.webpage import create_app


def load_config(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def _decode_jpeg_to_bgr(jpeg_bytes: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _get_best_local_ip() -> str:
    """
    Best-effort way to get the VM's primary LAN IP without external dependencies.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No traffic is actually sent for UDP connect; it's just used to pick an interface.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def arena_processing_loop(logger, arenacam, arena_processor: ArenaProcessor):
    last_frame_obj = None
    try:
        while True:
            frame = arenacam.latest_frame
            if frame is None:
                await asyncio.sleep(0.01)
                continue

            if frame is last_frame_obj:
                await asyncio.sleep(0.01)
                continue
            last_frame_obj = frame

            bgr = _decode_jpeg_to_bgr(frame)
            if bgr is None:
                logger.debug("Failed to decode JPEG frame")
                await asyncio.sleep(0.01)
                continue

            arena_processor.process_bgr(bgr)
            await asyncio.sleep(0)  # yield
    except asyncio.CancelledError:
        # clean exit
        return


async def run():
    config = load_config(Path(__file__).parent / "config.json")

    level = parse_level(config.get("system", {}).get("log_level", "INFO"), default=logging.INFO)
    logger = get_logger("main", level=level)

    cam_cfg = config.get("camera", {})
    fe_cfg = config.get("frontend", {})

    udp_host = cam_cfg.get("bind_ip", "0.0.0.0")
    udp_port = int(cam_cfg.get("bind_port", 5000))
    tcp_host = fe_cfg.get("host", "0.0.0.0")
    tcp_port = int(fe_cfg.get("port", 8080))

    ensure_ports_available(
        udp_host=udp_host,
        udp_port=udp_port,
        tcp_host=tcp_host,
        tcp_port=tcp_port,
    )

    arenacam = create_arenacam(
        ArenaCamConfig(
            mode=cam_cfg.get("mode", "rtp_h264"),
            bind_ip=udp_host,
            bind_port=udp_port,
            rtp_payload=int(cam_cfg.get("rtp_payload", 96)),
        )
    )
    await arenacam.start()

    # Marker layout you provided:
    # 0 BL, 1 TL, 2 TR, 3 BR
    # (Crop logic now only requires presence of 0-3; it auto-computes outer quad robustly.)
    arena_processor = ArenaProcessor(
        ArenaConfig(required_corner_ids=(0, 1, 2, 3))
    )

    proc_task = asyncio.create_task(arena_processing_loop(logger, arenacam, arena_processor))

    app = create_app(arenacam, arena_processor)
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, tcp_host, tcp_port)
    await site.start()

    ip = _get_best_local_ip()
    logger.info(f"Vision system running. Open http://{ip}:{tcp_port}/")

    try:
        while True:
            await asyncio.sleep(5)
    except KeyboardInterrupt:
        logger.info("Shutdown requested (Ctrl+C)")
    finally:
        # Stop processing task cleanly
        proc_task.cancel()
        try:
            await proc_task
        except asyncio.CancelledError:
            pass

        # Stop camera and frontend
        await arenacam.stop()
        await runner.cleanup()

        logger.info("Stopped cleanly")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
