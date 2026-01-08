import asyncio
import json
import logging
import signal
import socket
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from aiohttp import web

from utils.logging import get_logger, parse_level, web_info
from utils.port_guard import ensure_ports_available
from communications.arenacam import ArenaCamConfig, create_arenacam
from vision.arena import ArenaConfig, ArenaProcessor
from frontend.webpage import create_app
from communications.wifi_server import WifiServer


def load_config(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def _decode_jpeg_to_bgr(jpeg_bytes: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _get_best_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def arena_processing_loop(
    stop_event: asyncio.Event,
    arenacam,
    arena_processor: ArenaProcessor,
    target_fps: float = 30.0,
):
    frame_period = 1.0 / max(1.0, float(target_fps))
    try:
        while not stop_event.is_set():
            start = time.perf_counter()

            jpeg = arenacam.latest_frame
            if jpeg is not None:
                bgr = _decode_jpeg_to_bgr(jpeg)
                if bgr is not None:
                    await asyncio.to_thread(arena_processor.process_bgr, bgr)

            elapsed = time.perf_counter() - start
            sleep_time = frame_period - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                await asyncio.sleep(0)
    except asyncio.CancelledError:
        return


async def run():
    config = load_config(Path(__file__).parent / "config.json")

    level = parse_level(config.get("system", {}).get("log_level", "INFO"), default=logging.INFO)
    logger = get_logger("main", level=level)

    cam_cfg = config.get("camera", {})
    fe_cfg = config.get("frontend", {})
    wifi_cfg = config.get("wifi_server", {})

    udp_host = cam_cfg.get("bind_ip", "0.0.0.0")
    udp_port = int(cam_cfg.get("bind_port", 5000))

    web_host = fe_cfg.get("host", "0.0.0.0")
    web_port = int(fe_cfg.get("port", 8080))

    wifi_host = wifi_cfg.get("host", "0.0.0.0")
    wifi_port = int(wifi_cfg.get("port", 7755))

    ensure_ports_available(
        udp_host=udp_host,
        udp_port=udp_port,
        tcp_host=web_host,
        tcp_port=web_port,
    )
    # Also ensure wifi port isn't already in use
    ensure_ports_available(
        udp_host="0.0.0.0",
        udp_port=0,
        tcp_host=wifi_host,
        tcp_port=wifi_port,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_stop():
        if not stop_event.is_set():
            logger.info("Shutdown requested (Ctrl+C)")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    arenacam = create_arenacam(
        ArenaCamConfig(
            mode=cam_cfg.get("mode", "rtp_h264"),
            bind_ip=udp_host,
            bind_port=udp_port,
            rtp_payload=int(cam_cfg.get("rtp_payload", 96)),
        )
    )

    arena_processor = ArenaProcessor(
        ArenaConfig(
            id_bl=0,
            id_tl=1,
            id_tr=2,
            id_br=3,
            output_width=1000,
            output_height=500,
            crop_refresh_seconds=600,
            border_marker_fraction=0.5,
            vertical_padding_fraction=0.01,
            crop_jpeg_quality=75,
            overlay_jpeg_quality=80,
        )
    )

    def get_pose_for_id(marker_id: int) -> Tuple[float, float, float]:
        return arena_processor.poses_arena.get(marker_id, (-1.0, -1.0, -1.0))

    def is_seen(marker_id: int) -> bool:
        return marker_id in arena_processor.seen_ids

    wifi_server = WifiServer(
        host=wifi_host,
        port=wifi_port,
        get_marker_pose=get_pose_for_id,
        is_marker_seen=is_seen,
    )

    runner = None
    site = None
    proc_task = None

    try:
        await arenacam.start()

        proc_task = asyncio.create_task(
            arena_processing_loop(stop_event, arenacam, arena_processor, target_fps=30.0)
        )

        # Frontend web server
        app = create_app(stop_event, arenacam, arena_processor)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, web_host, web_port)
        await site.start()

        # ESP WiFi server
        await wifi_server.start()

        ip = _get_best_local_ip()
        logger.info(f"Vision system running. Open http://{ip}:{web_port}/")

        await stop_event.wait()

    except asyncio.CancelledError:
        stop_event.set()

    finally:
        stop_event.set()

        if proc_task is not None:
            proc_task.cancel()
            try:
                await asyncio.wait_for(proc_task, timeout=2.0)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        # Stop wifi server
        try:
            await asyncio.wait_for(wifi_server.stop(), timeout=3.0)
        except Exception:
            pass

        if site is not None:
            try:
                await asyncio.wait_for(site.stop(), timeout=2.0)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        if runner is not None:
            try:
                await asyncio.wait_for(runner.cleanup(), timeout=2.0)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        try:
            await asyncio.wait_for(arenacam.stop(), timeout=2.5)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

        logger.info("Stopped cleanly")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
