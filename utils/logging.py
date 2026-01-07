import logging
from typing import Callable, Dict, List, Optional, Set, Any

# =========================================
# Web event sink plumbing (System + Teams)
# =========================================

# Sink receives dict events, e.g.
# {"type":"system_log","line":"[INFO] ..."}
# {"type":"team_log","team":"Team A","line":"[INFO] ..."}
# {"type":"team_list","teams":["Team A","Team B"]}
_WEB_EVENT_SINK: Optional[Callable[[Dict[str, Any]], None]] = None

# Track teams seen so far (until you wire in real team presence)
_KNOWN_TEAMS: Set[str] = set()


def register_web_event_sink(sink: Callable[[Dict[str, Any]], None]) -> None:
    """
    Register a sink that receives web events (system logs, team logs, team list updates).
    The sink must be thread-safe on the caller side (webpage.py uses call_soon_threadsafe).
    """
    global _WEB_EVENT_SINK
    _WEB_EVENT_SINK = sink


def _emit_web_event(evt: Dict[str, Any]) -> None:
    sink = _WEB_EVENT_SINK
    if sink is None:
        return
    try:
        sink(evt)
    except Exception:
        # Never break normal logging due to web logging issues
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
    """
    Send a line to the webpage System Printouts.
    """
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
    """
    Replace the current team list (dynamic; call whenever your ESP/WS layer changes).
    Broadcasts the new list to the webpage.
    """
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


def team_log(team_name: str, level: str, message: str) -> None:
    """
    Log a line associated with a team. Shows in the Team column when that team is selected.
    """
    team = str(team_name).strip()
    if not team:
        # If no team is given, route to system printouts
        web_log(level, message)
        return

    # Auto-add team to list for now (until real presence is wired in)
    if team not in _KNOWN_TEAMS:
        _KNOWN_TEAMS.add(team)
        _emit_web_event({"type": "team_list", "teams": sorted(_KNOWN_TEAMS)})

    _emit_web_event({"type": "team_log", "team": team, "line": _format_line(level, message)})


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
