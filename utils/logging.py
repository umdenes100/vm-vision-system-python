import logging
import logging.handlers
from pathlib import Path
from typing import Optional

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)

# Use "WARN" (not "WARNING") for display to match your requested levels.
_LEVEL_DISPLAY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "FATAL",
}

# Supported config strings -> logging numeric levels
_LEVEL_PARSE = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,  # accept, but we'll display as WARN
    "ERROR": logging.ERROR,
    "FATAL": logging.CRITICAL,
    "CRITICAL": logging.CRITICAL,  # accept, but we'll display as FATAL
}


class BracketLevelFormatter(logging.Formatter):
    """
    Console formatter: [LEVEL] MESSAGE
    (WARN is shown as WARN, CRITICAL is shown as FATAL)
    """

    def format(self, record: logging.LogRecord) -> str:
        level_name = _LEVEL_DISPLAY.get(record.levelno, record.levelname)
        msg = record.getMessage()
        return f"[{level_name}] {msg}"


def parse_level(level_str: str, default: int = logging.INFO) -> int:
    if not level_str:
        return default
    return _LEVEL_PARSE.get(level_str.strip().upper(), default)


def get_logger(
    name: str,
    level: int = logging.INFO,
    filename: str = "vision_system.log",
    console: bool = True,
    file: bool = True,
) -> logging.Logger:
    """
    Create or return a configured logger.

    Behavior:
      - Emits only at `level` and worse severity.
      - Console format: [LEVEL] MESSAGE
      - File format: ISO-ish timestamp + level + logger + message
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if get_logger is called multiple times
    if logger.handlers:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    logger.propagate = False  # don't double-log via root handlers

    if console:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(BracketLevelFormatter())
        logger.addHandler(ch)

    if file:
        fh = logging.handlers.RotatingFileHandler(
            _LOG_DIR / filename,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
        )
        fh.setLevel(level)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            )
        )
        logger.addHandler(fh)

    return logger
