#!/usr/bin/env bash
set -euo pipefail

# =========================
# Config (sane defaults)
# =========================
VENV_PATH="${VENV_PATH:-.venv}"
SRC_OPENCV="${SRC_OPENCV:-$HOME/opencv}"                 # path to opencv source
SRC_OPENCV_CONTRIB="${SRC_OPENCV_CONTRIB:-$HOME/opencv_contrib}" # path to opencv_contrib source
BUILD_DIR="${BUILD_DIR:-$SRC_OPENCV/build}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
JOBS="${JOBS:-$(nproc)}"

# Behavior flags
FORCE=0        # continue even if python-like processes running
KILL=0         # kill python-like processes
NUMPY_MAJOR="${NUMPY_MAJOR:-2}"  # 1 = install numpy<2, 2 = install numpy>=2

# =========================
# Args
# =========================
usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --venv PATH                 Virtualenv path (default: ${VENV_PATH})
  --src-opencv PATH           OpenCV source directory (default: ${SRC_OPENCV})
  --src-opencv-contrib PATH   opencv_contrib source directory (default: ${SRC_OPENCV_CONTRIB})
  --build-dir PATH            Build directory (default: ${BUILD_DIR})
  --install-prefix PATH       CMAKE_INSTALL_PREFIX (default: ${INSTALL_PREFIX})
  --type {Release|Debug}      CMAKE_BUILD_TYPE (default: ${CMAKE_BUILD_TYPE})
  -j, --jobs N                Parallel build jobs (default: CPU cores)
  --numpy-major {1|2}         Pin NumPy major version (default: ${NUMPY_MAJOR})
  --force                     Ignore running Python/Jupyter processes
  --kill                      Kill running Python/Jupyter processes
  -h, --help                  Show this help
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv) VENV_PATH="$2"; shift 2;;
    --src-opencv) SRC_OPENCV="$2"; shift 2;;
    --src-opencv-contrib) SRC_OPENCV_CONTRIB="$2"; shift 2;;
    --build-dir) BUILD_DIR="$2"; shift 2;;
    --install-prefix) INSTALL_PREFIX="$2"; shift 2;;
    --type) CMAKE_BUILD_TYPE="$2"; shift 2;;
    -j|--jobs) JOBS="$2"; shift 2;;
    --numpy-major) NUMPY_MAJOR="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --kill) KILL=1; shift;;
    -h|--help) usage;;
    *) echo "[ERR] Unknown option: $1" >&2; usage;;
  esac
done

log()   { printf "[INFO] %s\n" "$*"; }
warn()  { printf "[WARN] %s\n" "$*" >&2; }
error() { printf "[ERR]  %s\n" "$*" >&2; }

# =========================
# Check Python-like processes
# =========================
log "Checking for running Python/IPython/Jupyter processes…"
if pgrep -faE 'python|ipython|jupyter' >/dev/null; then
  warn "Detected running Python-like processes:"
  pgrep -faE 'python|ipython|jupyter' || true

  if [[ $KILL -eq 1 ]]; then
    warn "Killing detected processes…"
    # shellcheck disable=SC2009
    ps -eo pid,command | awk '/python|ipython|jupyter/ && $2 !~ /grep/ {print $1}' | xargs -r kill -9 || true
  elif [[ $FORCE -ne 1 ]]; then
    error "Please stop these processes or rerun with --force or --kill."
    exit 1
  else
    warn "Continuing due to --force."
  fi
fi

# =========================
# Activate venv
# =========================
if [[ ! -f "${VENV_PATH}/bin/activate" ]]; then
  error "Venv not found at ${VENV_PATH}. Create it first (python -m venv ${VENV_PATH})."
  exit 1
fi
# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"
log "Using venv: $(python -c 'import sys,site; print(sys.executable)')"

# =========================
# Ensure pip + NumPy (before CMake!)
# =========================
log "Upgrading pip/setuptools/wheel…"
SITE_PKGS_DIR="${VENV_PATH}/lib/python$(python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"

# Ensure we can write inside the venv (common after accidental 'sudo pip')
if [[ ! -w "${SITE_PKGS_DIR}" ]]; then
  warn "site-packages is not writable: ${SITE_PKGS_DIR}"
  if command -v sudo >/dev/null 2>&1; then
    warn "Fixing ownership of the venv (sudo)…"
    sudo chown -R "$USER":"$USER" "${VENV_PATH}"
  else
    error "No sudo available to fix ownership. Please run:
      sudo chown -R \"$USER\":\"$USER\" \"${VENV_PATH}\""
    exit 1
  fi
fi

# extra safety: never allow pip outside the venv
export PIP_REQUIRE_VIRTUALENV=1

python -m pip install --upgrade "pip<25" setuptools wheel

if [[ "$NUMPY_MAJOR" == "1" ]]; then
  PIN='numpy<2'
elif [[ "$NUMPY_MAJOR" == "2" ]]; then
  PIN='numpy>=2'
else
  error "--numpy-major must be 1 or 2"
  exit 1
fi
log "Installing $PIN…"
python -m pip install "$PIN"

# =========================
# System build deps (incl. GStreamer dev headers)
# =========================
log "Ensuring build/runtime dependencies (apt)…"
sudo apt-get update -y
sudo apt-get install -y \
  build-essential cmake git pkg-config \
  libgtk-3-dev \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libavresample-dev \
  libxvidcore-dev libx264-dev libx265-dev libv4l-dev \
  libtbb-dev \
  # GStreamer headers (CRITICAL) + common runtime plugins
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-libav gstreamer1.0-tools

if ! pkg-config --exists gstreamer-1.0; then
  error "pkg-config cannot find gstreamer-1.0; GStreamer dev headers missing."
  exit 1
fi
log "GStreamer version: $(pkg-config --modversion gstreamer-1.0)"

# =========================
# Resolve Python + NumPy paths
# =========================
PYTHON_EXEC="$(command -v python)"
SITE_PKGS="$(python - <<'PY'
import site, sys
sp = getattr(site, 'getsitepackages', lambda: [])()
print(sp[0] if sp else site.getusersitepackages())
PY
)"
NUMPY_INC="$(python - <<'PY'
import numpy as np
print(np.get_include())
PY
)"

log "Python: ${PYTHON_EXEC}"
log "Python site-packages: ${SITE_PKGS}"
log "NumPy include: ${NUMPY_INC}"
log "NumPy version: $(python -c 'import numpy as np; print(np.__version__)')"

# =========================
# Prepare build dir (force clean reconfigure)
# =========================
mkdir -p "${BUILD_DIR}"
log "Cleaning build cache at ${BUILD_DIR}…"
rm -rf "${BUILD_DIR:?}/"*

# =========================
# CMake configure  (force GStreamer/FFmpeg/V4L ON)
# =========================
CMAKE_ARGS=(
  -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
  -DCMAKE_INSTALL_PREFIX="${INSTALL_PREFIX}"
  -DOPENCV_GENERATE_PKGCONFIG=ON
  -DBUILD_TESTS=OFF
  -DBUILD_PERF_TESTS=OFF
  -DOPENCV_ENABLE_NONFREE=ON

  # Backends: explicitly ON
  -DWITH_GSTREAMER=ON
  -DWITH_FFMPEG=ON
  -DWITH_V4L=ON
  -DWITH_TBB=ON

  # Python wiring
  -DBUILD_opencv_python3=ON
  -DPYTHON3_EXECUTABLE="${PYTHON_EXEC}"
  -DPYTHON3_PACKAGES_PATH="${SITE_PKGS}"
  -DPYTHON3_NUMPY_INCLUDE_DIRS="${NUMPY_INC}"
)

# opencv_contrib (optional but nice)
if [[ -d "${SRC_OPENCV_CONTRIB}/modules" ]]; then
  CMAKE_ARGS+=(-DOPENCV_EXTRA_MODULES_PATH="${SRC_OPENCV_CONTRIB}/modules")
fi

log "Configuring OpenCV with CMake…"
(
  cd "${BUILD_DIR}"
  cmake "${CMAKE_ARGS[@]}" "${SRC_OPENCV}"
  echo "----- Backend summary (grep) -----"
  grep -E "GStreamer|FFMPEG|V4L|TBB" CMakeCache.txt || true
)

# =========================
# Build & install
# =========================
log "Building OpenCV (jobs: ${JOBS})…"
cmake --build "${BUILD_DIR}" -- -j"${JOBS}"

log "Installing to ${INSTALL_PREFIX} (sudo may prompt)…"
sudo cmake --install "${BUILD_DIR}"
sudo ldconfig

# =========================
# Verify import & GStreamer
# =========================
log "Verifying OpenCV Python import + GStreamer…"
python - <<'PY'
import re, sys
import numpy as np
try:
    import cv2
except Exception as e:
    print("FAILED to import cv2:", e)
    sys.exit(1)

print("numpy:", np.__version__)
print("opencv:", cv2.__version__)

info = cv2.getBuildInformation()
gst_line = next((l for l in info.splitlines() if "GStreamer" in l), "")
print(gst_line or "No 'GStreamer' line found in build info.")
if not re.search(r"GStreamer\s*:\s*YES", info, re.I):
    print("FAIL: OpenCV built without GStreamer support.")
    sys.exit(2)

# Try a trivial GStreamer pipeline if plugins are present
caps = cv2.VideoCapture("videotestsrc num-buffers=1 ! videoconvert ! appsink", cv2.CAP_GSTREAMER)
print("GStreamer CAP opened:", caps.isOpened())
caps.release()
PY

log "Done ✅"
