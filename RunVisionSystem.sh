#!/usr/bin/env bash
set -euo pipefail

# Always run from this repo’s root (where this script lives)
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ">>> Vision System Starting"
echo ">>> Attempting to acquire lock..."

# optional: your existing lock logic here
# (kept as-is if you already have it in this script)

# Ensure venv exists and is usable
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
source .venv/bin/activate

# Safety: avoid accidental global pip installs
export PIP_REQUIRE_VIRTUALENV=1

# Make sure pip itself is OK (pin below 25 for py3.10 if needed)
python - <<'PY' || true
import sys, subprocess
# pip 25 drops py3.8 but 3.10 is fine—still, be conservative if needed
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

# Node (if you need it). Remove if your app doesn’t need nvm.
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  . "$HOME/.nvm/nvm.sh"
  nvm use 18 >/dev/null || true
fi

export QT_QPA_PLATFORM=offscreen

# Run the app
exec python main.py "$@"
