import logging
from typing import Callable, Dict, Optional, Any, Set, List

_WEB_EVENT_SINK: Optional[Callable[[Dict[str, Any]], None]] = None
_KNOWN_TEAMS: Set[str] = set()


def register_web_event_sink(sink: Callable[[Dict[str, Any]], None]) -> None:
    global _WEB_EVENT_SINK
    _WEB_EVENT_SINK = sink


def _emit_web_event(evt: Dict[str, Any]) -> None:
    sink = _WEB_EVENT_SINK
    if sink is None:
        return
    try:
        sink(evt)
    except Exception:
        pass


def _format_line(level: str, message: str) -> str:
    lvl = (level or "INFO").upper()
    if lvl == "WARNING":
        lvl = "WARN"
    if lvl == "CRITICAL":
        lvl = "FATAL"
    return f"[{lvl}] {message}"


# -------------------------
# System Printouts helpers
# -------------------------

def web_log(level: str, message: str) -> None:
    _emit_web_event({"type": "system_log", "line": _format_line(level, message)})


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


# -------------------------
# Team Printouts helpers
# -------------------------

def set_team_list(teams: List[str]) -> None:
    global _KNOWN_TEAMS
    cleaned = []
    seen = set()
    for t in teams:
        name = str(t).strip()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        cleaned.append(name)

    _KNOWN_TEAMS = set(cleaned)
    _emit_web_event({"type": "team_list", "teams": cleaned})


def emit_team_roster(teams: List[Dict[str, Any]]) -> None:
    _emit_web_event({"type": "team_roster", "teams": teams})


def _ensure_team_known(team: str) -> None:
    global _KNOWN_TEAMS
    if team not in _KNOWN_TEAMS:
        _KNOWN_TEAMS.add(team)
        _emit_web_event({"type": "team_list", "teams": sorted(_KNOWN_TEAMS)})


def team_log(team_name: str, level: str, message: str) -> None:
    """
    Team log WITH [LEVEL] prefix.
    """
    team = str(team_name).strip()
    if not team:
        web_log(level, message)
        return

    _ensure_team_known(team)
    _emit_web_event({"type": "team_log", "team": team, "line": _format_line(level, message)})


def team_raw(team_name: str, message: str) -> None:
    """
    Team log WITHOUT any [LEVEL] prefix.
    Intended for ESP-originated prints.
    """
    team = str(team_name).strip()
    if not team:
        return

    _ensure_team_known(team)
    _emit_web_event({"type": "team_raw", "team": team, "line": str(message)})


def team_debug(team_name: str, message: str) -> None:
    team_log(team_name, "DEBUG", message)


def team_info(team_name: str, message: str) -> None:
    team_log(team_name, "INFO", message)


def team_warn(team_name: str, message: str) -> None:
    team_log(team_name, "WARN", message)


def team_error(team_name: str, message: str) -> None:
    team_log(team_name, "ERROR", message)


def team_fatal(team_name: str, message: str) -> None:
    team_log(team_name, "FATAL", message)


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
