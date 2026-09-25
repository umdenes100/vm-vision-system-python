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


# Special exit code used to tell run.sh:
#
#     "The user requested a restart."
#
# run.sh sees 42, cleans all application ports, and launches a
# completely fresh Python process.
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

        if Path(
            models_dir
        ).is_absolute():

            env[
                "VISION_ML_MODELS_DIR"
            ] = str(
                models_dir
            )

        else:

            env[
                "VISION_ML_MODELS_DIR"
            ] = str(
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

                stdout=(
                    asyncio.subprocess.PIPE
                ),

                stderr=(
                    asyncio.subprocess.STDOUT
                ),

                env=env,
            )
        )

        async def _stdout_pump():

            assert (
                proc.stdout
                is not None
            )

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

        stdout_task = (
            asyncio.create_task(
                _stdout_pump()
            )
        )

        logger.info(
            "[ml] Listener started"
        )

        return (
            proc,
            stdout_task,
        )

    except Exception as e:

        logger.error(
            "[ml] Failed to start "
            f"listener: {e}"
        )

        return None, None


async def run():

    # =========================================================
    # CONFIGURATION
    # =========================================================

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

    communications_cfg = (
        config.get(
            "communications",
            {},
        )
    )

    # =========================================================
    # PORTS
    # =========================================================

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

    ws_host = (
        communications_cfg.get(
            "ws_host",
            tcp_host,
        )
    )

    ws_port = int(
        communications_cfg.get(
            "ws_port",
            7755,
        )
    )

    # run.sh performs the aggressive cleanup before launching
    # Python. This remains as a final safety check.
    ensure_ports_available(
        udp_host=udp_host,
        udp_port=udp_port,

        tcp_host=tcp_host,
        tcp_port=tcp_port,

        extra_tcp_ports=[
            ws_port
        ],
    )

    # =========================================================
    # STATE
    # =========================================================

    stop_event = (
        asyncio.Event()
    )

    restart_requested = False

    loop = (
        asyncio.get_running_loop()
    )

    # =========================================================
    # SIGNAL HANDLING
    # =========================================================

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
            "Clean restart requested "
            "from web UI"
        )

        # Allow the restart HTTP response to actually reach
        # the browser before we begin shutting things down.
        await asyncio.sleep(
            0.15
        )

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

    # =========================================================
    # CAMERA
    # =========================================================

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

    # =========================================================
    # COMPONENT REFERENCES
    # =========================================================

    runner = None
    site = None

    proc_task = None

    wifi_server = None

    ml_proc = None
    ml_stdout_task = None

    # =========================================================
    # START APPLICATION
    # =========================================================

    try:

        # -----------------------------------------------------
        # MACHINE LEARNING
        # -----------------------------------------------------

        (
            ml_proc,
            ml_stdout_task,
        ) = await _start_ml_listener(
            config,
            logger,
        )

        # -----------------------------------------------------
        # GSTREAMER
        # -----------------------------------------------------

        await arenacam.start()

        # -----------------------------------------------------
        # ARENA PROCESSOR
        # -----------------------------------------------------

        arena_processor = (
            ArenaProcessor(
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
        )

        proc_task = (
            asyncio.create_task(
                arena_processing_loop(
                    stop_event,
                    logger,
                    arenacam,
                    arena_processor,
                    target_fps=30.0,
                )
            )
        )

        # -----------------------------------------------------
        # ESP WEBSOCKET
        # -----------------------------------------------------

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
                arena_processor
                .seen_ids
            )

            seen = (
                seen_obj()
                if callable(
                    seen_obj
                )
                else seen_obj
            )

            return (
                marker_id
                in seen
            )

        models_dir = (
            config.get(
                "machinelearning",
                {},
            ).get(
                "models_dir"
            )
        )

        wifi_server = WifiServer(
            host=ws_host,
            port=ws_port,

            get_marker_pose=(
                _get_pose
            ),

            is_marker_seen=(
                _is_seen
            ),

            models_dir=(
                models_dir
            ),
        )

        await wifi_server.start()

        logger.info(
            "ESP WebSocket server "
            "listening on "
            f"ws://{_get_best_local_ip()}:"
            f"{ws_port}/ws"
        )

        # -----------------------------------------------------
        # WEBSITE
        # -----------------------------------------------------

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

            restart_password=(
                restart_password
            ),

            restart_callback=(
                _request_restart
            ),
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

        ip = (
            _get_best_local_ip()
        )

        logger.info(
            "Vision system running. "
            f"Open http://{ip}:"
            f"{tcp_port}/"
        )

        # -----------------------------------------------------
        # WAIT UNTIL STOP OR RESTART
        # -----------------------------------------------------

        await stop_event.wait()

    except asyncio.CancelledError:
        pass

    # =========================================================
    # FAST RESTART PATH
    # =========================================================
    #
    # THIS PATH IS INTENTIONALLY DIFFERENT FROM NORMAL SHUTDOWN.
    #
    # We do NOT:
    #
    #     runner.cleanup()
    #     wait for HTTP clients
    #     wait for asyncio.run() to unwind
    #
    # The browser may have long-running HTTP/MJPEG connections.
    #
    # GStreamer's stdout reader may also have blocking executor
    # work outstanding.
    #
    # Either one can prevent asyncio.run() from completing.
    #
    # Therefore:
    #
    #     1. Cancel arena processing
    #     2. Try to stop GStreamer
    #     3. Terminate ML
    #     4. Flush logs
    #     5. os._exit(42)
    #
    # run.sh then performs the authoritative cleanup.
    # =========================================================

    finally:

        stop_event.set()

        if restart_requested:

            logger.warning(
                "Performing FAST "
                "restart shutdown"
            )

            # -------------------------------------------------
            # ARENA PROCESSING
            # -------------------------------------------------

            if proc_task is not None:

                logger.info(
                    "Cancelling arena "
                    "processing task"
                )

                proc_task.cancel()

            # -------------------------------------------------
            # GSTREAMER
            # -------------------------------------------------

            logger.info(
                "Stopping GStreamer "
                "for restart..."
            )

            try:

                await asyncio.wait_for(
                    arenacam.stop(),
                    timeout=1.0,
                )

                logger.info(
                    "GStreamer stopped"
                )

            except asyncio.TimeoutError:

                logger.warning(
                    "GStreamer stop exceeded "
                    "1 second; run.sh will "
                    "force cleanup"
                )

            except Exception as e:

                logger.warning(
                    "GStreamer stop error: "
                    f"{e}"
                )

            # -------------------------------------------------
            # ML PROCESS
            # -------------------------------------------------

            if ml_proc is not None:

                logger.info(
                    "Terminating ML listener"
                )

                try:
                    ml_proc.terminate()

                except (
                    ProcessLookupError
                ):
                    pass

                except Exception:
                    pass

            if (
                ml_stdout_task
                is not None
            ):

                ml_stdout_task.cancel()

            # -------------------------------------------------
            # EXIT IMMEDIATELY
            # -------------------------------------------------

            logger.warning(
                "Fast restart cleanup "
                "complete"
            )

            logger.warning(
                "Immediately exiting "
                "process with restart "
                f"code {RESTART_EXIT_CODE}"
            )

            # Make sure the last logs actually reach the
            # terminal before _exit bypasses normal cleanup.
            try:
                sys.stdout.flush()
            except Exception:
                pass

            try:
                sys.stderr.flush()
            except Exception:
                pass

            # IMPORTANT:
            #
            # Do NOT:
            #
            #     return
            #     sys.exit()
            #     raise SystemExit()
            #
            # All of those eventually pass control back through
            # asyncio.run(), which attempts to shut down its
            # default executor.
            #
            # Blocking GStreamer stdout reads can prevent that
            # executor shutdown from completing.
            #
            # os._exit() immediately terminates THIS Python
            # process.
            #
            # run.sh receives status 42 and takes over.
            os._exit(
                RESTART_EXIT_CODE
            )

        # =====================================================
        # NORMAL SHUTDOWN
        # =====================================================
        #
        # Ctrl+C and SIGTERM still use graceful shutdown.
        # =====================================================

        logger.info(
            "Beginning normal "
            "clean shutdown"
        )

        # -----------------------------------------------------
        # WEBSITE LISTENER
        # -----------------------------------------------------

        if site is not None:

            logger.info(
                "Stopping web site..."
            )

            try:

                await asyncio.wait_for(
                    site.stop(),
                    timeout=1.0,
                )

                logger.info(
                    "Web site stopped"
                )

            except asyncio.TimeoutError:

                logger.warning(
                    "Web site shutdown "
                    "timed out"
                )

            except Exception as e:

                logger.warning(
                    "Web site shutdown "
                    f"error: {e}"
                )

        # -----------------------------------------------------
        # AIOHTTP RUNNER
        # -----------------------------------------------------

        if runner is not None:

            logger.info(
                "Cleaning web runner..."
            )

            try:

                await asyncio.wait_for(
                    runner.cleanup(),
                    timeout=1.0,
                )

                logger.info(
                    "Web runner cleaned"
                )

            except asyncio.TimeoutError:

                logger.warning(
                    "Web runner cleanup "
                    "timed out"
                )

            except Exception as e:

                logger.warning(
                    "Web runner cleanup "
                    f"error: {e}"
                )

        # -----------------------------------------------------
        # ESP WEBSOCKET
        # -----------------------------------------------------

        if wifi_server is not None:

            logger.info(
                "Stopping ESP "
                "WebSocket server..."
            )

            try:

                await asyncio.wait_for(
                    wifi_server.stop(),
                    timeout=1.0,
                )

                logger.info(
                    "ESP WebSocket "
                    "server stopped"
                )

            except asyncio.TimeoutError:

                logger.warning(
                    "ESP WebSocket "
                    "shutdown timed out"
                )

            except Exception as e:

                logger.warning(
                    "ESP WebSocket "
                    "shutdown error: "
                    f"{e}"
                )

        # -----------------------------------------------------
        # ARENA PROCESSING
        # -----------------------------------------------------

        if proc_task is not None:

            logger.info(
                "Stopping arena "
                "processing task..."
            )

            proc_task.cancel()

            try:

                await asyncio.wait_for(
                    proc_task,
                    timeout=0.5,
                )

            except (
                asyncio.CancelledError,
                asyncio.TimeoutError,
            ):
                pass

            except Exception:
                pass

            logger.info(
                "Arena processing "
                "task stopped"
            )

        # -----------------------------------------------------
        # GSTREAMER
        # -----------------------------------------------------

        logger.info(
            "Stopping ArenaCam / "
            "GStreamer..."
        )

        try:

            await asyncio.wait_for(
                arenacam.stop(),
                timeout=2.0,
            )

            logger.info(
                "ArenaCam / "
                "GStreamer stopped"
            )

        except asyncio.TimeoutError:

            logger.warning(
                "ArenaCam shutdown "
                "timed out"
            )

        except Exception as e:

            logger.warning(
                "ArenaCam shutdown "
                f"error: {e}"
            )

        # -----------------------------------------------------
        # ML LISTENER
        # -----------------------------------------------------

        if ml_proc is not None:

            logger.info(
                "Stopping ML listener..."
            )

            try:
                ml_proc.terminate()

            except (
                ProcessLookupError
            ):
                pass

            except Exception:
                pass

            try:

                await asyncio.wait_for(
                    ml_proc.wait(),
                    timeout=1.0,
                )

            except asyncio.TimeoutError:

                logger.warning(
                    "ML listener did not "
                    "terminate; killing it"
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

            except Exception:
                pass

        if (
            ml_stdout_task
            is not None
        ):

            ml_stdout_task.cancel()

        logger.info(
            "Stopped cleanly"
        )


def main():

    asyncio.run(
        run()
    )


if __name__ == "__main__":
    main()
