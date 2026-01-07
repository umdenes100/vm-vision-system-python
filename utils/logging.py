import logging
import logging.handlers
import os
from pathlib import Path

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)


def get_logger(
    name: str,
    level: int = logging.INFO,
    filename: str = "vision_system.log",
) -> logging.Logger:
    """
    Create or return a configured logger.

    Args:
        name: Logger name (usually __name__)
        level: Logging level
        filename: Log file name inside ./logs/

    Returns:
        logging.Logger
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Prevent duplicate handlers

    logger.setLevel(level)

    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setFormatter(log_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
