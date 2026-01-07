import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web

from utils.logging import get_logger, parse_level
from communications.arenacam import ArenaCamConfig, create_arenacam
from frontend.webpage import create_app


def load_config(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


async def run():
    config = load_config(Path(__file__).parent / "config.json")

    level = parse_level(config.get("system", {}).get("log_level", "INFO"), default=logging.INFO)
    logger = get_logger("main", level=level)

    cam_cfg = config.get("camera", {})
    arenacam = create_arenacam(
        ArenaCamConfig(
            mode=cam_cfg.get("mode", "rtp_h264"),
            bind_ip=cam_cfg.get("bind_ip", "0.0.0.0"),
            bind_port=int(cam_cfg.get("bind_port", 5000)),
            rtp_payload=int(cam_cfg.get("rtp_payload", 96)),
        )
    )

    await arenacam.start()

    app = create_app(arenacam)
    runner = web.AppRunner(app)
    await runner.setup()

    frontend_cfg = config.get("frontend", {})
    host = frontend_cfg.get("host", "0.0.0.0")
    port = int(frontend_cfg.get("port", 8080))

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"Vision system running. Open http://<VM_IP>:{port}/")

    try:
        while True:
            await asyncio.sleep(5)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        await arenacam.stop()
        await runner.cleanup()
        logger.info("Stopped")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
