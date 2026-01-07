import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web
from utils.logging import get_logger, parse_level
from communications.arenacam import ArenaCamUDP, ArenaCamConfig
from frontend.webpage import create_app


def load_config(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


async def run():
    config = load_config(Path(__file__).parent / "config.json")

    level = parse_level(config["system"].get("log_level", "INFO"))
    logger = get_logger("main", level=level)

    cam_cfg = config["camera_udp"]
    arenacam = ArenaCamUDP(
        ArenaCamConfig(cam_cfg["bind_ip"], cam_cfg["bind_port"])
    )
    await arenacam.start()

    app = create_app(arenacam)
    runner = web.AppRunner(app)
    await runner.setup()

    frontend_cfg = config["frontend"]
    site = web.TCPSite(
        runner,
        frontend_cfg["host"],
        frontend_cfg["port"],
    )
    await site.start()

    logger.info("Vision system running")

    try:
        while True:
            await asyncio.sleep(5)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        await arenacam.stop()
        await runner.cleanup()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
