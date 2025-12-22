#!/usr/bin/env bash
set -euo pipefail

# Always run from this repo’s root (where this script lives)
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ">>> Vision System Starting"

# -----------------------------------------------------------------------------
# Hard "single instance" lock: do not allow this script to be run twice.
# -----------------------------------------------------------------------------
LOCK_FILE="$SCRIPT_DIR/.visionsystem.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: Vision System is already running (lock held: $LOCK_FILE)." >&2
  echo "       Stop the running instance before starting another." >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# Ensure venv exists and is usable
# -----------------------------------------------------------------------------
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# Make sure venv isn’t root-owned (common cause of pip perms errors)
if [[ ! -w ".venv/lib" ]]; then
  if command -v sudo >/dev/null 2>&1; then
    echo ">>> Fixing venv ownership (sudo)…"
    sudo chown -R "$USER":"$USER" .venv
  else
    echo "ERROR: .venv not writable and no sudo available" >&2
    exit 1
  fi
fi

# Activate venv
# shellcheck disable=SC1091
source .venv/bin/activate

# Safety: avoid accidental global pip installs
export PIP_REQUIRE_VIRTUALENV=1

# Make sure pip itself is OK (pin below 25 to be conservative)
python - <<'PY' || true
import sys, subprocess
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "pip<25", "setuptools", "wheel"], check=True)
PY

# Keep NumPy <2 to match your OpenCV build ABI
NUMPY_VER="$(python - <<'PY'
try:
    import importlib.metadata as md
    print(md.version("numpy"))
except Exception:
    print("")
PY
)"
if [[ -z "${NUMPY_VER}" || "${NUMPY_VER%%.*}" -ge 2 ]]; then
  echo ">>> Installing NumPy <2 for OpenCV compatibility…"
  pip install -q --upgrade 'numpy<2'
fi

# Quick sanity check that OpenCV can import with this NumPy
python - <<'PY'
import numpy as np
import cv2
print(f">>> OpenCV {cv2.__version__} with NumPy {np.__version__} OK")
PY

# -----------------------------------------------------------------------------
# Node setup + Firebase listener (REQUIRED)
# -----------------------------------------------------------------------------
LISTENER="$SCRIPT_DIR/components/machinelearning/listen.mjs"
if [[ ! -f "$LISTENER" ]]; then
  echo "ERROR: Firebase listener not found at: $LISTENER" >&2
  exit 1
fi

# Node (nvm). Required because listen.mjs is required.
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  . "$HOME/.nvm/nvm.sh"
  nvm use 18 >/dev/null || true
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is not available in PATH (required for listen.mjs)." >&2
  exit 1
fi

# Environment
export QT_QPA_PLATFORM=offscreen
export OPENCV_LOG_LEVEL=ERROR
export GST_DEBUG=0

# -----------------------------------------------------------------------------
# Start both processes and supervise:
# - If listen.mjs exits -> terminate Python and exit non-zero
# - If Python exits -> terminate listener and exit with Python status
# - Ctrl-C / TERM kills both
# -----------------------------------------------------------------------------
NODE_PID=""
PY_PID=""

cleanup() {
  # Avoid set -e killing cleanup
  set +e

  if [[ -n "${PY_PID}" ]] && kill -0 "${PY_PID}" >/dev/null 2>&1; then
    kill "${PY_PID}" >/dev/null 2>&1
    wait "${PY_PID}" >/dev/null 2>&1
  fi

  if [[ -n "${NODE_PID}" ]] && kill -0 "${NODE_PID}" >/dev/null 2>&1; then
    kill "${NODE_PID}" >/dev/null 2>&1
    wait "${NODE_PID}" >/dev/null 2>&1
  fi
}
trap cleanup INT TERM EXIT

echo ">>> Starting Firebase listener (required)..."
node "$LISTENER" >/dev/null 2>&1 &
NODE_PID=$!

# Fail fast if listener dies immediately (syntax error, missing deps, auth crash, etc.)
sleep 1
if ! kill -0 "$NODE_PID" >/dev/null 2>&1; then
  echo "ERROR: Firebase listener (listen.mjs) failed to start or exited immediately." >&2
  echo "       (Output is currently silenced; remove redirection to debug.)" >&2
  exit 1
fi
echo ">>> Firebase listener running (pid $NODE_PID)"

echo ">>> Starting Python vision system..."
python main.py "$@" &
PY_PID=$!
echo ">>> Python running (pid $PY_PID)"

# Wait until either process exits; treat listener exit as fatal.
while true; do
  if ! kill -0 "$NODE_PID" >/dev/null 2>&1; then
    echo "ERROR: Firebase listener exited. Shutting down Vision System." >&2
    # Cleanup trap will kill python too, but do it explicitly for clarity.
    if kill -0 "$PY_PID" >/dev/null 2>&1; then
      kill "$PY_PID" >/dev/null 2>&1
    fi
    wait "$PY_PID" >/dev/null 2>&1 || true
    exit 1
  fi

  if ! kill -0 "$PY_PID" >/dev/null 2>&1; then
    # Python exited; propagate its exit code and stop the listener
    wait "$PY_PID"
    PY_STATUS=$?
    echo ">>> Python exited (status $PY_STATUS). Stopping Firebase listener."
    if kill -0 "$NODE_PID" >/dev/null 2>&1; then
      kill "$NODE_PID" >/dev/null 2>&1
      wait "$NODE_PID" >/dev/null 2>&1 || true
    fi
    exit "$PY_STATUS"
  fi

  sleep 0.5
done
