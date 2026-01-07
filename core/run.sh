#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PY="${VENV_DIR}/bin/python"

echo "[run] Starting vision system"

if [[ ! -x "$PY" ]]; then
  echo "[run] ERROR: venv python not found at $PY"
  echo "[run] Did you run install/install.sh ?"
  exit 1
fi

# Start python in background so we can control shutdown even if it hangs
"$PY" "${ROOT_DIR}/core/main.py" &
PID=$!

_cleanup() {
  local sig="${1:-INT}"
  if kill -0 "$PID" 2>/dev/null; then
    echo "[run] Sending SIG${sig} to PID ${PID}"
    kill "-${sig}" "$PID" 2>/dev/null || true
  fi
}

# On Ctrl+C / termination: try graceful shutdown, then force if needed
_on_signal() {
  echo "[run] Ctrl+C received - requesting shutdown"
  _cleanup "INT"

  # Wait up to 3 seconds for graceful exit
  for _ in {1..30}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      wait "$PID" 2>/dev/null || true
      exit 0
    fi
    sleep 0.1
  done

  echo "[run] Graceful shutdown timed out - sending SIGTERM"
  _cleanup "TERM"

  # Wait up to 2 more seconds
  for _ in {1..20}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      wait "$PID" 2>/dev/null || true
      exit 0
    fi
    sleep 0.1
  done

  echo "[run] Still running - sending SIGKILL"
  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
  fi
  wait "$PID" 2>/dev/null || true
  exit 0
}

trap _on_signal INT TERM

# Wait for python normally
wait "$PID"
