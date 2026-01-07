import logging
from typing import Callable, Optional

# =========================
# Web log sink plumbing
# =========================

_WEB_SINK: Optional[Callable[[str], None]] = None


def register_web_sink(sink: Callable[[str], None]) -> None:
    """
    Register a function that receives log lines for the webpage System Printouts.
    The sink should accept a single string line (already formatted).
    """
    global _WEB_SINK
    _WEB_SINK = sink


def _emit_web(line: str) -> None:
    sink = _WEB_SINK
    if sink is None:
        return
    try:
        sink(line)
    except Exception:
        # Never let web logging break normal logging
        pass


def web_log(level: str, message: str) -> None:
    """
    Send a line to the webpage System Printouts.
    Format matches console: [LEVEL] MESSAGE
    """
    lvl = (level or "INFO").upper()
    _emit_web(f"[{lvl}] {message}")


def web_debug(message: str) -> None:
    web_log("DEBUG", message)


def web_info(message: str) -> None:
    web_log("INFO", message)


def web_warn(message: str) -> None:
    web_log("WARN", message)


def web_error(message: str) -> None:
    web_log("ERROR", message)


def web_fatal(message: str) -> None:
    web_log("FATAL", message)


# =========================
# Console logger
# =========================

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "FATAL": logging.CRITICAL,
    "CRITICAL": logging.CRITICAL,
}


def parse_level(level_str: str, default: int = logging.INFO) -> int:
    if not level_str:
        return default
    return _LEVEL_MAP.get(level_str.strip().upper(), default)


class _BracketFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        lvl = record.levelname
        if lvl == "WARNING":
            lvl = "WARN"
        if lvl == "CRITICAL":
            lvl = "FATAL"
        return f"[{lvl}] {record.getMessage()}"


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_BracketFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger
