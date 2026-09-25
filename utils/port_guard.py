import os
import shutil
import signal
import socket
import subprocess
import time
from contextlib import closing
from typing import Iterable, Optional

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
    extra_tcp_ports: Optional[list[int]] = None,
) -> None:
    """Verify that every port required by the vision system is free."""
    logger = get_logger("port_guard")

    udp_err = _try_bind_udp(udp_host, udp_port)
    if udp_err is not None:
        logger.fatal(f"UDP port not available: {udp_host}:{udp_port} ({udp_err})")
        raise RuntimeError(f"UDP port in use: {udp_host}:{udp_port}")

    ports = [int(tcp_port)] + [int(p) for p in (extra_tcp_ports or [])]
    for p in ports:
        tcp_err = _try_bind_tcp(tcp_host, p)
        if tcp_err is not None:
            logger.fatal(f"TCP port not available: {tcp_host}:{p} ({tcp_err})")
            raise RuntimeError(f"TCP port in use: {tcp_host}:{p}")

    extras = "" if not (extra_tcp_ports or []) else f", extra TCP {extra_tcp_ports}"
    logger.info(f"Ports OK: UDP {udp_host}:{udp_port}, TCP {tcp_host}:{tcp_port}{extras}")


def _pids_from_fuser(port: int, protocol: str) -> set[int]:
    if shutil.which("fuser") is None:
        return set()

    try:
        result = subprocess.run(
            ["fuser", f"{int(port)}/{protocol}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
            check=False,
        )
    except Exception:
        return set()

    pids: set[int] = set()
    for token in result.stdout.split():
        try:
            pids.add(int(token))
        except ValueError:
            pass
    return pids


def _pids_from_lsof(port: int, protocol: str) -> set[int]:
    if shutil.which("lsof") is None:
        return set()

    proto = protocol.lower()
    args = ["lsof", "-nP", "-t"]
    if proto == "tcp":
        args += [f"-iTCP:{int(port)}"]
    else:
        args += [f"-iUDP:{int(port)}"]

    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
            check=False,
        )
    except Exception:
        return set()

    pids: set[int] = set()
    for token in result.stdout.split():
        try:
            pids.add(int(token))
        except ValueError:
            pass
    return pids


def _find_port_pids(port: int, protocol: str) -> set[int]:
    pids = _pids_from_fuser(port, protocol)
    if not pids:
        pids = _pids_from_lsof(port, protocol)
    pids.discard(os.getpid())
    pids.discard(os.getppid())
    return pids


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def terminate_port_owners(
    ports: Iterable[tuple[int, str]],
    term_timeout: float = 1.0,
) -> None:
    """
    Best-effort cleanup for stale processes still owning this application's ports.

    Call this only after this process has closed its own sockets/subprocesses.
    It sends SIGTERM first, waits briefly, then SIGKILLs anything still alive.
    Supported protocols are "tcp" and "udp".
    """
    logger = get_logger("port_guard")

    victims: set[int] = set()
    normalized: list[tuple[int, str]] = []

    for port, protocol in ports:
        protocol = protocol.lower().strip()
        if protocol not in ("tcp", "udp"):
            raise ValueError(f"Unsupported protocol: {protocol}")
        port = int(port)
        normalized.append((port, protocol))
        found = _find_port_pids(port, protocol)
        if found:
            logger.warning(
                f"Found stale process(es) on {protocol.upper()} port {port}: "
                + ", ".join(str(pid) for pid in sorted(found))
            )
        victims.update(found)

    if not victims:
        logger.info("Restart port sweep: no stale port owners found")
        return

    for pid in sorted(victims):
        try:
            os.kill(pid, signal.SIGTERM)
            logger.warning(f"Sent SIGTERM to stale PID {pid}")
        except ProcessLookupError:
            pass
        except PermissionError:
            logger.error(f"Permission denied while terminating stale PID {pid}")

    deadline = time.monotonic() + max(0.0, float(term_timeout))
    while time.monotonic() < deadline:
        if not any(_pid_exists(pid) for pid in victims):
            break
        time.sleep(0.05)

    for pid in sorted(victims):
        if not _pid_exists(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            logger.warning(f"Sent SIGKILL to stale PID {pid}")
        except ProcessLookupError:
            pass
        except PermissionError:
            logger.error(f"Permission denied while killing stale PID {pid}")

    time.sleep(0.1)

    leftovers: list[str] = []
    for port, protocol in normalized:
        pids = _find_port_pids(port, protocol)
        if pids:
            leftovers.append(f"{protocol.upper()} {port}: {sorted(pids)}")

    if leftovers:
        raise RuntimeError(
            "Restart port sweep could not free all ports: " + "; ".join(leftovers)
        )

    logger.info("Restart port sweep complete; all configured ports are free")
