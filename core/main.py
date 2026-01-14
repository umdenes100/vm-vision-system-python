import asyncio
import json
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from aiohttp import web

from utils.logging import get_logger, parse_level
from utils.port_guard import ensure_ports_available
from communications.arenacam import ArenaCamConfig, create_arenacam
from communications.wifi_server import WifiServer
from vision.arena import ArenaConfig, ArenaProcessor
from frontend.webpage import create_app


def load_config(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def _decode_jpeg_to_bgr(jpeg_bytes: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _get_best_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't need to be reachable; just forces OS to pick a route + local IP.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def arena_processing_loop(
    stop_event: asyncio.Event,
    logger,
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


async def _start_ml_listener(config: dict, logger):
    """
    Starts the legacy ML listener process (machinelearning/listener.py) in a subprocess.
    """
    ml_cfg = config.get("machinelearning", {})
    if not ml_cfg.get("enabled", True):
        return None, None

    repo_root = Path(__file__).resolve().parents[1]
    listener_path = repo_root / "machinelearning" / "listener.py"

    env = os.environ.copy()
    models_dir = ml_cfg.get("models_dir")
    if models_dir:
        env["VISION_ML_MODELS_DIR"] = str(
            (repo_root / models_dir).resolve() if not Path(models_dir).is_absolute() else models_dir
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            str(listener_path),
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )

        async def _stdout_pump():
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                # ML listener prints become system log lines
                logger.info(line.decode("utf-8", errors="replace").rstrip("\n"))

        stdout_task = asyncio.create_task(_stdout_pump())
        logger.info("[ml] Listener started")
        return proc, stdout_task
    except Exception as e:
        logger.error(f"[ml] Failed to start listener: {e}")
        return None, None


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

    # ESP WebSocket server settings (defaults)
    ws_host = config.get("communications", {}).get("ws_host", tcp_host)
    ws_port = int(config.get("communications", {}).get("ws_port", 7755))

    # Port guard: camera UDP + web TCP + ESP WS TCP
    ensure_ports_available(
        udp_host=udp_host,
        udp_port=udp_port,
        tcp_host=tcp_host,
        tcp_port=tcp_port,
        extra_tcp_ports=[ws_port],
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

    runner = None
    site = None
    proc_task = None
    wifi_server = None
    ml_proc = None
    ml_stdout_task = None

    try:
        # ML listener (subprocess)
        ml_proc, ml_stdout_task = await _start_ml_listener(config, logger)

        await arenacam.start()

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

        # Start arena processing loop
        proc_task = asyncio.create_task(
            arena_processing_loop(stop_event, logger, arenacam, arena_processor, target_fps=30.0)
        )

        # ---- START ESP WS SERVER (THIS WAS MISSING) ----
        def _get_pose(marker_id: int):
            return arena_processor.poses_arena.get(marker_id, (-1.0, -1.0, -1.0))

        def _is_seen(marker_id: int) -> bool:
            return marker_id in arena_processor.seen_ids()

        models_dir = config.get("machinelearning", {}).get("models_dir")
        wifi_server = WifiServer(
            host=ws_host,
            port=ws_port,
            get_marker_pose=_get_pose,
            is_marker_seen=_is_seen,
            models_dir=models_dir,
        )
        await wifi_server.start()
        logger.info(f"ESP WebSocket server listening on ws://{_get_best_local_ip()}:{ws_port}/ws")
        # -----------------------------------------------

        # Frontend server
        app = create_app(stop_event, arenacam, arena_processor)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, tcp_host, tcp_port)
        await site.start()

        ip = _get_best_local_ip()
        logger.info(f"Vision system running. Open http://{ip}:{tcp_port}/")

        await stop_event.wait()

    except asyncio.CancelledError:
        pass
    finally:
        stop_event.set()

        # Stop ML listener first
        if ml_proc is not None:
            try:
                ml_proc.terminate()
            except ProcessLookupError:
                pass
            except Exception:
                pass

        if ml_stdout_task is not None:
            ml_stdout_task.cancel()
            try:
                await asyncio.wait_for(ml_stdout_task, timeout=1.0)
            except Exception:
                pass

        if ml_proc is not None:
            try:
                await asyncio.wait_for(ml_proc.wait(), timeout=2.0)
            except Exception:
                try:
                    ml_proc.kill()
                except Exception:
                    pass

        # Stop wifi_server
        if wifi_server is not None:
            try:
                await asyncio.wait_for(wifi_server.stop(), timeout=2.5)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        # Stop arena processing loop
        if proc_task is not None:
            proc_task.cancel()
            try:
                await asyncio.wait_for(proc_task, timeout=1.0)
            except Exception:
                pass

        # Stop web server
        if site is not None:
            try:
                await site.stop()
            except Exception:
                pass

        if runner is not None:
            try:
                await asyncio.wait_for(runner.cleanup(), timeout=2.0)
            except Exception:
                pass

        # Stop camera ingest
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
