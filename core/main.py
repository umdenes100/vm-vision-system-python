import json
import logging
from pathlib import Path

from utils.logging import get_logger


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r") as f:
        return json.load(f)


def main() -> None:
    config_path = Path(__file__).parent / "config.json"
    config = load_config(config_path)

    log_level_str = config["system"].get("log_level", "INFO")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    logger = get_logger("main", level=log_level)

    logger.info("Vision system starting")
    logger.info("Loaded configuration")
    logger.debug("Config contents: %s", config)

    # Placeholder for future subsystems
    logger.info("System initialized (no subsystems active)")

    try:
        while True:
            pass  # Main loop placeholder
    except KeyboardInterrupt:
        logger.info("Shutdown requested (KeyboardInterrupt)")
    finally:
        logger.info("Vision system stopped")


if __name__ == "__main__":
    main()
