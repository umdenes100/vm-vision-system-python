#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Vision System — One-Command Installer (Ubuntu 22.04 Jammy)
# ============================================================
# Preps system deps, Python venv, Python deps, verifies
# OpenCV+GStreamer, and builds OpenCV from source (contrib)
# with a robust cv2 loader fix for venvs.
#
# Usage:
#   chmod +x install_vision_system.sh
#   ./install_vision_system.sh
#
# Env options:
#   VENV_PATH       (default: .venv)
#   BUILD_OPENCV    auto|always|never (default: auto)
#   OPENCV_VERSION  (default: 4.8.1)
#   OPENCV_JOBS     (default: nproc)
# ============================================================

VENV_PATH="${VENV_PATH:-.venv}"
BUILD_OPENCV="${BUILD_OPENCV:-auto}"
OPENCV_VERSION="${OPENCV_VERSION:-4.8.1}"
OPENCV_JOBS="${OPENCV_JOBS:-$(nproc)}"

REPO_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo ">>> Installer starting in: $REPO_DIR"

# ----------------------------
# Helpers
# ----------------------------
apt_lock_aware() {
  local tries=30
  local delay=10
  local cmd="$*"
  for ((i=1; i<=tries; i++)); do
    if sudo bash -lc "$cmd"; then
      return 0
    fi
    if fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || fuser /var/lib/apt/lists/lock >/dev/null 2>&1; then
      echo "APT is busy (attempt $i/$tries). Retrying in ${delay}s…"
      sleep "$delay"
    else
      echo "APT command failed for a non-lock reason."
      return 1
    fi
  done
  echo "Gave up waiting for APT lock."
  return 1
}

py_fix_cv2_loader_and_test() {
  python - <<'PY'
import sys, sysconfig, pathlib, importlib.machinery, importlib.util
from glob import glob

def site_candidates():
    cand = []
    paths = sysconfig.get_paths()
    for key in ("purelib","platlib","stdlib","data"):
        p = paths.get(key)
        if p:
            cand.append(pathlib.Path(p))
    # venv prefix explicit fallbacks
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    cand += [
        pathlib.Path(sys.prefix)/"lib"/pyver/"site-packages",
        pathlib.Path(sys.prefix)/"lib"/pyver/"dist-packages",
    ]
    # de-dup, keep existing only
    out = []
    seen = set()
    for c in cand:
        if c not in seen and c.exists():
            seen.add(c); out.append(c)
    return out

def ensure_loader_and_test():
    ok=False
    last_err=None
    for s in site_candidates():
        pkg = s/"cv2"
        bin_dir = pkg/f"python-{sys.version_info.major}.{sys.version_info.minor}"
        # Common wheel layout includes cv2/__init__.py already; source install puts .so under python-X.Y
        sos = []
        if bin_dir.exists():
            sos = list(bin_dir.glob("cv2*.so"))
        # Some builds might drop the .so directly under cv2/
        if not sos and pkg.exists():
            sos = list(pkg.glob("cv2*.so"))
        if not sos:
            continue
        # Guarantee package dir exists and has a loader
        pkg.mkdir(parents=True, exist_ok=True)
        init = pkg/"__init__.py"
        if not init.exists():
            init.write_text(
                "import sys, pathlib, importlib.machinery, importlib.util\n"
                "_pkg = pathlib.Path(__file__).resolve().parent\n"
                f"_dirs = [_pkg / f\"python-{{sys.version_info.major}}.{{sys.version_info.minor}}\", _pkg]\n"
                "_so = None\n"
                "import re\n"
                "for d in _dirs:\n"
                "    if d.exists():\n"
                "        cands = sorted([p for p in d.glob('cv2*.so')])\n"
                "        if cands:\n"
                "            _so = cands[0]; break\n"
                "if _so is None:\n"
                "    raise ImportError('OpenCV binary .so not found for this Python version')\n"
                "_ldr = importlib.machinery.ExtensionFileLoader('cv2', str(_so))\n"
                "_spec = importlib.util.spec_from_file_location('cv2', str(_so), loader=_ldr)\n"
                "_mod = importlib.util.module_from_spec(_spec)\n"
                "_ldr.exec_module(_mod)\n"
                "globals().update(_mod.__dict__)\n"
            )
            print(f\"Wrote loader: {init}\")
        try:
            import cv2  # noqa: F401
            cap = cv2.VideoCapture('videotestsrc num-buffers=1 ! videoconvert ! appsink', cv2.CAP_GSTREAMER)
            ok = bool(cap.isOpened())
            cap.release()
            print('CAP_GSTREAMER opened:', ok)
            return ok
        except Exception as e:
            last_err = e
    if not ok and last_err:
        print('cv2 import/test failed:', last_err)
    return ok

if not ensure_loader_and_test():
    sys.exit(2)
PY
}

# ----------------------------
# Sanity checks
# ----------------------------
if ! command -v lsb_release >/dev/null 2>&1; then
  echo "lsb_release not found. Installing…"
  apt_lock_aware "apt-get update -y"
  apt_lock_aware "apt-get install -y lsb-release"
fi

UBU_VER="$(lsb_release -rs || true)"
if [[ "${UBU_VER}" != 22.04* ]]; then
  echo "WARNING: Detected Ubuntu ${UBU_VER}. This script targets 22.04 (Jammy). Continuing anyway…"
fi

# ----------------------------
# System packages
# ----------------------------
echo ">>> Installing system dependencies (apt)…"
apt_lock_aware "apt-get update -y"
apt_lock_aware "apt-get install -y \
  python3 python3-venv python3-pip \
  build-essential cmake git pkg-config \
  v4l-utils \
  libgtk-3-dev \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
  libxvidcore-dev libx264-dev libx265-dev libv4l-dev \
  libtbb-dev \
  gstreamer1.0-tools gstreamer1.0-libav \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
  qttools5-dev-tools qttools5-dev"

echo ">>> GStreamer version: $(pkg-config --modversion gstreamer-1.0 || echo 'unknown')"

# ----------------------------
# Python venv
# ----------------------------
if [[ ! -d "${VENV_PATH}" ]]; then
  echo ">>> Creating venv at ${VENV_PATH}…"
  python3 -m venv "${VENV_PATH}"
fi

# Ensure venv ownership (avoid root-owned venv)
if [[ ! -w "${VENV_PATH}" ]]; then
  echo ">>> Fixing venv ownership (sudo)…"
  sudo chown -R "$USER":"$USER" "${VENV_PATH}"
fi

# Activate venv
# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"
export PIP_REQUIRE_VIRTUALENV=1

# Upgrade pip/setuptools/wheel (pip<25 is safe across py3.10)
python - <<'PY'
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "pip<25", "setuptools", "wheel"], check=True)
PY

# ----------------------------
# Python requirements
# ----------------------------
REQ_FILE="requirements.txt"
if [[ ! -f "$REQ_FILE" ]]; then
  echo "ERROR: requirements.txt not found next to this installer."
  exit 1
fi

echo ">>> Installing Python dependencies from $REQ_FILE…"
python -m pip install -r "$REQ_FILE"

# Hard-ensure NumPy major <2
python - <<'PY'
import importlib.metadata as md, subprocess, sys
try:
    v = md.version("numpy")
    major = int(v.split(".")[0])
except Exception:
    major = 0
if major >= 2:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "numpy<2"], check=True)
PY

# ----------------------------
# Detect whether OpenCV with GStreamer works
# ----------------------------
echo ">>> Checking OpenCV + GStreamer availability…"
set +e
python - <<'PY'
import sys
ok=False
try:
    import cv2
    cap = cv2.VideoCapture("videotestsrc num-buffers=1 ! videoconvert ! appsink", cv2.CAP_GSTREAMER)
    ok = bool(cap.isOpened())
    cap.release()
except Exception as e:
    ok=False
print("CHECK:", "OK" if ok else "NO")
sys.exit(0 if ok else 3)
PY
CHECK_RC=$?
set -e

NEED_BUILD=0
case "$BUILD_OPENCV" in
  always) NEED_BUILD=1 ;;
  never)  NEED_BUILD=0 ;;
  auto)   if [[ $CHECK_RC -ne 0 ]]; then NEED_BUILD=1; fi ;;
  *) echo "Invalid BUILD_OPENCV=$BUILD_OPENCV (use auto|always|never)"; exit 2 ;;
esac

# ----------------------------
# Build OpenCV from source (if required)
# ----------------------------
if [[ $NEED_BUILD -eq 1 ]]; then
  echo ">>> OpenCV lacks GStreamer support (or BUILD_OPENCV=always). Building OpenCV ${OPENCV_VERSION} from source…"

  OPENCV_SRC="${HOME}/opencv"
  OPENCV_CONTRIB_SRC="${HOME}/opencv_contrib"
  OPENCV_BUILD="${OPENCV_SRC}/build"

  # Fetch sources
  if [[ ! -d "${OPENCV_SRC}/.git" ]]; then
    git clone --depth=1 --branch "${OPENCV_VERSION}" https://github.com/opencv/opencv.git "${OPENCV_SRC}"
  else
    (cd "${OPENCV_SRC}" && git fetch --depth=1 origin "${OPENCV_VERSION}" && git checkout "${OPENCV_VERSION}")
  fi

  if [[ ! -d "${OPENCV_CONTRIB_SRC}/.git" ]]; then
    git clone --depth=1 --branch "${OPENCV_VERSION}" https://github.com/opencv/opencv_contrib.git "${OPENCV_CONTRIB_SRC}"
  else
    (cd "${OPENCV_CONTRIB_SRC}" && git fetch --depth=1 origin "${OPENCV_VERSION}" && git checkout "${OPENCV_VERSION}")
  fi

  # Resolve Python paths for binding
  PY_EXEC="$(command -v python)"
  SITE_PKGS="$(python - <<'PY'
import sysconfig; print(sysconfig.get_paths().get("purelib",""))
PY
)"
  NUMPY_INC="$(python - <<'PY'
import numpy as np; print(np.get_include())
PY
)"

  # Clean build dir
  rm -rf "${OPENCV_BUILD}"
  mkdir -p "${OPENCV_BUILD}"

  cmake -S "${OPENCV_SRC}" -B "${OPENCV_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DOPENCV_GENERATE_PKGCONFIG=ON \
    -DBUILD_TESTS=OFF \
    -DBUILD_PERF_TESTS=OFF \
    -DOPENCV_ENABLE_NONFREE=ON \
    -DWITH_GSTREAMER=ON \
    -DWITH_FFMPEG=ON \
    -DWITH_V4L=ON \
    -DWITH_TBB=ON \
    -DBUILD_opencv_python3=ON \
    -DOPENCV_EXTRA_MODULES_PATH="${OPENCV_CONTRIB_SRC}/modules" \
    -DPYTHON3_EXECUTABLE="${PY_EXEC}" \
    -DPYTHON3_PACKAGES_PATH="${SITE_PKGS}" \
    -DPYTHON3_NUMPY_INCLUDE_DIRS="${NUMPY_INC}"

  cmake --build "${OPENCV_BUILD}" -- -j"${OPENCV_JOBS}"
  sudo cmake --install "${OPENCV_BUILD}"
  sudo ldconfig

  # Remove wheel OpenCV if present to avoid module confusion
  python -m pip uninstall -y opencv-python opencv-contrib-python || true

  echo ">>> Verifying OpenCV + GStreamer after build…"
  if ! py_fix_cv2_loader_and_test; then
    echo "OpenCV Python binding test failed."
    exit 2
  fi
fi

# ----------------------------
# Fix cv2 loader if OpenCV installed but Python import is broken
# ----------------------------
if ! py_fix_cv2_loader_and_test; then
  echo "OpenCV Python binding test failed."
  exit 2
fi

# ----------------------------
# Desktop integration & runner
# ----------------------------
echo ">>> Setting executable bit on RunVisionSystem.sh…"
chmod +x "${REPO_DIR}/RunVisionSystem.sh" || true

if [[ -f "${REPO_DIR}/runner.desktop" ]]; then
  echo ">>> Copying desktop shortcut to ~/Desktop…"
  mkdir -p "${HOME}/Desktop"
  cp -f "${REPO_DIR}/runner.desktop" "${HOME}/Desktop/runner.desktop"
  # Rewrite Exec to absolute RunVisionSystem.sh path if present
  if command -v sed >/dev/null 2>&1; then
    sed -i "s|^Exec=.*|Exec=${REPO_DIR}/RunVisionSystem.sh|g" "${HOME}/Desktop/runner.desktop" || true
  fi
  chmod +x "${HOME}/Desktop/runner.desktop" || true
else
  echo "NOTE: runner.desktop not found in repo; skipping desktop shortcut."
fi

# ----------------------------
# Final notes & smoke test
# ----------------------------
echo ">>> Installation complete."
echo ">>> You can launch the app via:"
echo "    ${REPO_DIR}/RunVisionSystem.sh"
echo ">>> If using GNOME, you may need to right-click the Desktop shortcut and choose 'Allow Launching' once."
echo ">>> Optional quick smoke test (no network):"
echo "    python - <<'PY'"
echo "    import cv2; cap=cv2.VideoCapture('videotestsrc num-buffers=1 ! videoconvert ! appsink', cv2.CAP_GSTREAMER); print('CAP:', cap.isOpened())"
echo "    PY"
