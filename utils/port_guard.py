import socket
from contextlib import closing
from typing import Optional

from utils.logging import get_logger


def _try_bind_tcp(host: str, port: int) -> Optional[str]:
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return None
    except OSError as e:
        return str(e)


def _try_bind_udp(host: str, port: int) -> Optional[str]:
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
            s.bind((host, port))
            return None
    except OSError as e:
        return str(e)


def ensure_ports_available(
    udp_host: str,
    udp_port: int,
    tcp_host: str,
    tcp_port: int,
) -> None:
    """
    Ensures the ports required by the system are available.

    - UDP port for camera ingest (RTP/H264 stream)
    - TCP port for frontend web server

    If any are unavailable, logs a fatal and raises RuntimeError.
    """
    logger = get_logger("port_guard")

    udp_err = _try_bind_udp(udp_host, udp_port)
    if udp_err is not None:
        logger.fatal(f"UDP port not available: {udp_host}:{udp_port} ({udp_err})")
        raise RuntimeError(f"UDP port in use: {udp_host}:{udp_port}")

    tcp_err = _try_bind_tcp(tcp_host, tcp_port)
    if tcp_err is not None:
        logger.fatal(f"TCP port not available: {tcp_host}:{tcp_port} ({tcp_err})")
        raise RuntimeError(f"TCP port in use: {tcp_host}:{tcp_port}")

    logger.info(f"Ports OK: UDP {udp_host}:{udp_port}, TCP {tcp_host}:{tcp_port}")
