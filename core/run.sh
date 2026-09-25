#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PY="${VENV_DIR}/bin/python"

export PYTHONPATH="${ROOT_DIR}"

# Ports owned by this application. Clean them before every launch so a stale
# Python/GStreamer process from a previous run cannot block startup.
TCP_PORTS=(8080 7755)
UDP_PORTS=(5000)

kill_port() {
  local proto="$1"
  local port="$2"
  local pids=""

  # fuser is preferred because it can distinguish TCP/UDP sockets.
  if command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n "$proto" "$port" 2>/dev/null || true)"
  elif command -v lsof >/dev/null 2>&1; then
    if [[ "$proto" == "tcp" ]]; then
      pids="$(lsof -nP -t -iTCP:"$port" 2>/dev/null || true)"
    else
      pids="$(lsof -nP -t -iUDP:"$port" 2>/dev/null || true)"
    fi
  fi

  [[ -z "${pids//[[:space:]]/}" ]] && return 0

  echo "[run] Cleaning stale ${proto^^} port ${port} (PID(s): ${pids//$'\n'/ })"

  # First give every owner a chance to exit cleanly.
  kill -TERM $pids 2>/dev/null || true
  for _ in {1..20}; do
    local alive=0
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then alive=1; break; fi
    done
    [[ "$alive" -eq 0 ]] && return 0
    sleep 0.1
  done

  # A zombie/stuck child must not be allowed to keep the application port.
  echo "[run] Port ${port} still occupied; forcing termination"
  kill -KILL $pids 2>/dev/null || true
  sleep 0.2
}

clean_application_ports() {
  echo "[run] Checking for stale vision-system processes"
  for port in "${TCP_PORTS[@]}"; do kill_port tcp "$port"; done
  for port in "${UDP_PORTS[@]}"; do kill_port udp "$port"; done
}

echo "[run] Starting vision system"

if [[ ! -x "$PY" ]]; then
  echo "[run] ERROR: venv python not found at $PY"
  echo "[run] Did you run install/install.sh ?"
  exit 1
fi

# Always start from clean application ports. This specifically clears stale
# gst-launch/Python owners of UDP 5000 before main.py performs its port guard.
clean_application_ports

# Start Python in the background so this wrapper can control shutdown.
"$PY" "${ROOT_DIR}/core/main.py" &
PID=$!

_cleanup() {
  local sig="${1:-INT}"
  if kill -0 "$PID" 2>/dev/null; then
    echo "[run] Sending SIG${sig} to PID ${PID}"
    kill "-${sig}" "$PID" 2>/dev/null || true
  fi
}

_on_signal() {
  echo "[run] Shutdown requested"
  _cleanup "INT"

  for _ in {1..30}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      wait "$PID" 2>/dev/null || true
      clean_application_ports
      exit 0
    fi
    sleep 0.1
  done

  echo "[run] Graceful shutdown timed out - sending SIGTERM"
  _cleanup "TERM"

  for _ in {1..20}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      wait "$PID" 2>/dev/null || true
      clean_application_ports
      exit 0
    fi
    sleep 0.1
  done

  echo "[run] Still running - sending SIGKILL"
  kill -KILL "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
  clean_application_ports
  exit 0
}

trap _on_signal INT TERM

set +e
wait "$PID"
STATUS=$?
set -e

# If main.py exits abnormally, do not leave its detached children behind.
clean_application_ports
exit "$STATUS"
