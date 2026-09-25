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
from communications.arenacam import (
    ArenaCamConfig,
    create_arenacam,
)
from communications.wifi_server import WifiServer
from vision.arena import ArenaConfig, ArenaProcessor
from frontend.webpage import create_app


# run.sh watches for this exit code and performs a completely
# fresh launch after cleaning all application ports.
RESTART_EXIT_CODE = 42


def load_config(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def _decode_jpeg_to_bgr(
    jpeg_bytes: bytes,
) -> Optional[np.ndarray]:

    arr = np.frombuffer(
        jpeg_bytes,
        dtype=np.uint8,
    )

    return cv2.imdecode(
        arr,
        cv2.IMREAD_COLOR,
    )


def _get_best_local_ip() -> str:
    try:
        s = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        s.connect(
            ("8.8.8.8", 80)
        )

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
    frame_period = (
        1.0
        / max(
            1.0,
            float(target_fps),
        )
    )

    try:
        while not stop_event.is_set():
            start = time.perf_counter()

            jpeg = arenacam.latest_frame

            if jpeg is not None:
                bgr = _decode_jpeg_to_bgr(
                    jpeg
                )

                if bgr is not None:
                    await asyncio.to_thread(
                        arena_processor.process_bgr,
                        bgr,
                    )

            elapsed = (
                time.perf_counter()
                - start
            )

            sleep_time = (
                frame_period
                - elapsed
            )

            if sleep_time > 0:
                await asyncio.sleep(
                    sleep_time
                )
            else:
                await asyncio.sleep(0)

    except asyncio.CancelledError:
        return


async def _start_ml_listener(
    config: dict,
    logger,
):
    ml_cfg = config.get(
        "machinelearning",
        {},
    )

    if not ml_cfg.get(
        "enabled",
        True,
    ):
        return None, None

    repo_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    listener_path = (
        repo_root
        / "machinelearning"
        / "listener.py"
    )

    env = os.environ.copy()

    models_dir = ml_cfg.get(
        "models_dir"
    )

    if models_dir:
        if Path(models_dir).is_absolute():
            env["VISION_ML_MODELS_DIR"] = (
                str(models_dir)
            )
        else:
            env["VISION_ML_MODELS_DIR"] = str(
                (
                    repo_root
                    / models_dir
                ).resolve()
            )

    try:
        proc = (
            await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                str(listener_path),
                cwd=str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
        )

        async def _stdout_pump():
            assert proc.stdout is not None

            while True:
                line = (
                    await proc.stdout.readline()
                )

                if not line:
                    break

                logger.info(
                    line.decode(
                        "utf-8",
                        errors="replace",
                    ).rstrip("\n")
                )

        stdout_task = asyncio.create_task(
            _stdout_pump()
        )

        logger.info(
            "[ml] Listener started"
        )

        return proc, stdout_task

    except Exception as e:
        logger.error(
            f"[ml] Failed to start listener: {e}"
        )

        return None, None


async def _safe_shutdown_step(
    logger,
    name: str,
    awaitable,
    timeout: float,
):
    """
    Run one shutdown operation with a hard timeout.

    Shutdown must never be allowed to block a restart forever.
    """

    logger.info(
        f"Stopping {name}..."
    )

    try:
        await asyncio.wait_for(
            awaitable,
            timeout=timeout,
        )

        logger.info(
            f"{name} stopped"
        )

        return True

    except asyncio.TimeoutError:
        logger.warning(
            f"{name} shutdown timed out after "
            f"{timeout:.1f}s; continuing"
        )

        return False

    except asyncio.CancelledError:
        logger.warning(
            f"{name} shutdown was cancelled; continuing"
        )

        return False

    except Exception as e:
        logger.warning(
            f"Error stopping {name}: {e}"
        )

        return False


async def run() -> bool:
    config = load_config(
        Path(__file__).parent
        / "config.json"
    )

    level = parse_level(
        config.get(
            "system",
            {},
        ).get(
            "log_level",
            "INFO",
        ),
        default=logging.INFO,
    )

    logger = get_logger(
        "main",
        level=level,
    )

    cam_cfg = config.get(
        "camera",
        {},
    )

    fe_cfg = config.get(
        "frontend",
        {},
    )

    communications_cfg = config.get(
        "communications",
        {},
    )

    udp_host = cam_cfg.get(
        "bind_ip",
        "0.0.0.0",
    )

    udp_port = int(
        cam_cfg.get(
            "bind_port",
            5000,
        )
    )

    tcp_host = fe_cfg.get(
        "host",
        "0.0.0.0",
    )

    tcp_port = int(
        fe_cfg.get(
            "port",
            8080,
        )
    )

    ws_host = communications_cfg.get(
        "ws_host",
        tcp_host,
    )

    ws_port = int(
        communications_cfg.get(
            "ws_port",
            7755,
        )
    )

    # run.sh performs aggressive cleanup before launching us.
    # This remains as a final sanity check.
    ensure_ports_available(
        udp_host=udp_host,
        udp_port=udp_port,
        tcp_host=tcp_host,
        tcp_port=tcp_port,
        extra_tcp_ports=[
            ws_port
        ],
    )

    stop_event = asyncio.Event()

    restart_requested = False

    loop = asyncio.get_running_loop()

    def _request_stop():
        if not stop_event.is_set():
            logger.info(
                "Shutdown requested"
            )

            stop_event.set()

    async def _request_restart():
        nonlocal restart_requested

        if restart_requested:
            return

        restart_requested = True

        logger.warning(
            "Clean restart requested from web UI"
        )

        # Give the HTTP restart response time to reach the
        # browser before shutting down aiohttp.
        await asyncio.sleep(0.25)

        stop_event.set()

    for sig in (
        signal.SIGINT,
        signal.SIGTERM,
    ):
        try:
            loop.add_signal_handler(
                sig,
                _request_stop,
            )

        except NotImplementedError:
            pass

    arenacam = create_arenacam(
        ArenaCamConfig(
            mode=cam_cfg.get(
                "mode",
                "rtp_h264",
            ),
            bind_ip=udp_host,
            bind_port=udp_port,
            rtp_payload=int(
                cam_cfg.get(
                    "rtp_payload",
                    96,
                )
            ),
        )
    )

    runner = None
    site = None
    proc_task = None
    wifi_server = None

    ml_proc = None
    ml_stdout_task = None

    try:

        # =========================================================
        # MACHINE LEARNING
        # =========================================================

        ml_proc, ml_stdout_task = (
            await _start_ml_listener(
                config,
                logger,
            )
        )

        # =========================================================
        # CAMERA / GSTREAMER
        # =========================================================

        await arenacam.start()

        # =========================================================
        # ARENA PROCESSING
        # =========================================================

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

        proc_task = asyncio.create_task(
            arena_processing_loop(
                stop_event,
                logger,
                arenacam,
                arena_processor,
                target_fps=30.0,
            )
        )

        # =========================================================
        # ESP WEBSOCKET SERVER
        # =========================================================

        def _get_pose(
            marker_id: int,
        ):
            return (
                arena_processor
                .poses_arena
                .get(
                    marker_id,
                    (
                        -1.0,
                        -1.0,
                        -1.0,
                    ),
                )
            )

        def _is_seen(
            marker_id: int,
        ) -> bool:

            seen_obj = (
                arena_processor.seen_ids
            )

            seen = (
                seen_obj()
                if callable(seen_obj)
                else seen_obj
            )

            return marker_id in seen

        models_dir = config.get(
            "machinelearning",
            {},
        ).get(
            "models_dir"
        )

        wifi_server = WifiServer(
            host=ws_host,
            port=ws_port,
            get_marker_pose=_get_pose,
            is_marker_seen=_is_seen,
            models_dir=models_dir,
        )

        await wifi_server.start()

        logger.info(
            "ESP WebSocket server listening on "
            f"ws://{_get_best_local_ip()}:{ws_port}/ws"
        )

        # =========================================================
        # WEBSITE
        # =========================================================

        restart_password = str(
            fe_cfg.get(
                "restart_password",
                "",
            )
        ).strip()

        app = create_app(
            stop_event,
            arenacam,
            arena_processor,
            restart_password=restart_password,
            restart_callback=_request_restart,
        )

        runner = web.AppRunner(
            app
        )

        await runner.setup()

        site = web.TCPSite(
            runner,
            tcp_host,
            tcp_port,
        )

        await site.start()

        ip = _get_best_local_ip()

        logger.info(
            "Vision system running. "
            f"Open http://{ip}:{tcp_port}/"
        )

        # =========================================================
        # WAIT
        # =========================================================

        await stop_event.wait()

    except asyncio.CancelledError:
        pass

    finally:

        # =========================================================
        # CLEAN SHUTDOWN
        #
        # Nothing in here is allowed to hang indefinitely.
        #
        # If something refuses to die, run.sh will kill anything
        # remaining on the application ports before relaunching.
        # =========================================================

        stop_event.set()

        logger.info(
            "Beginning clean shutdown"
        )

        # =========================================================
        # 1. STOP WEB LISTENER
        # =========================================================

        if site is not None:

            await _safe_shutdown_step(
                logger,
                "web site",
                site.stop(),
                1.0,
            )

        # =========================================================
        # 2. CLEAN AIOHTTP RUNNER
        # =========================================================

        if runner is not None:

            await _safe_shutdown_step(
                logger,
                "web runner",
                runner.cleanup(),
                1.0,
            )

        # =========================================================
        # 3. STOP ESP WEBSOCKET SERVER
        # =========================================================

        if wifi_server is not None:

            await _safe_shutdown_step(
                logger,
                "ESP WebSocket server",
                wifi_server.stop(),
                1.0,
            )

        # =========================================================
        # 4. STOP ARENA PROCESSING
        # =========================================================

        if proc_task is not None:

            logger.info(
                "Stopping arena processing task..."
            )

            proc_task.cancel()

            try:
                await asyncio.wait_for(
                    proc_task,
                    timeout=0.5,
                )

            except asyncio.CancelledError:
                pass

            except asyncio.TimeoutError:
                logger.warning(
                    "Arena processing task did not stop "
                    "within 0.5s; continuing"
                )

            except Exception as e:
                logger.warning(
                    "Arena processing task shutdown "
                    f"error: {e}"
                )

            logger.info(
                "Arena processing task stopped"
            )

        # =========================================================
        # 5. STOP GSTREAMER
        # =========================================================

        logger.info(
            "Stopping ArenaCam / GStreamer..."
        )

        try:
            await asyncio.wait_for(
                arenacam.stop(),
                timeout=3.0,
            )

            logger.info(
                "ArenaCam / GStreamer stopped"
            )

        except asyncio.TimeoutError:
            logger.warning(
                "ArenaCam / GStreamer shutdown timed out. "
                "run.sh will force cleanup."
            )

        except asyncio.CancelledError:
            logger.warning(
                "ArenaCam / GStreamer shutdown cancelled. "
                "run.sh will force cleanup."
            )

        except Exception as e:
            logger.warning(
                "ArenaCam / GStreamer shutdown error: "
                f"{e}"
            )

        # =========================================================
        # 6. STOP ML LISTENER
        # =========================================================

        if ml_proc is not None:

            logger.info(
                "Stopping ML listener..."
            )

            try:
                ml_proc.terminate()

            except ProcessLookupError:
                pass

            except Exception as e:
                logger.warning(
                    "ML listener terminate error: "
                    f"{e}"
                )

        if ml_stdout_task is not None:

            ml_stdout_task.cancel()

            try:
                await asyncio.wait_for(
                    ml_stdout_task,
                    timeout=0.5,
                )

            except asyncio.CancelledError:
                pass

            except asyncio.TimeoutError:
                logger.warning(
                    "ML stdout task did not stop "
                    "within 0.5s"
                )

            except Exception:
                pass

        if ml_proc is not None:

            try:
                await asyncio.wait_for(
                    ml_proc.wait(),
                    timeout=1.0,
                )

            except asyncio.TimeoutError:

                logger.warning(
                    "ML listener did not terminate; "
                    "sending SIGKILL"
                )

                try:
                    ml_proc.kill()

                except Exception:
                    pass

                try:
                    await asyncio.wait_for(
                        ml_proc.wait(),
                        timeout=0.5,
                    )

                except Exception:
                    pass

        # =========================================================
        # DONE
        # =========================================================

        logger.info(
            "Stopped cleanly"
        )

    return restart_requested


def main():

    restart_requested = asyncio.run(
        run()
    )

    if restart_requested:

        # IMPORTANT:
        #
        # Do NOT os.exec() here.
        #
        # Exit completely and allow run.sh to:
        #
        #   - observe exit code 42
        #   - clean ports 5000 / 7755 / 8080
        #   - kill any remaining stale processes
        #   - start an entirely new Python process
        #   - start a new GStreamer pipeline
        #
        # This is much more reliable than trying to restart the
        # application inside the existing Python process.

        raise SystemExit(
            RESTART_EXIT_CODE
        )

    raise SystemExit(0)


if __name__ == "__main__":
    main()
