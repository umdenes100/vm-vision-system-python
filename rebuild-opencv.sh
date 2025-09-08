#!/usr/bin/env bash
set -euo pipefail

### ---------------------------------------------------------------------------
### Configuration (defaults; can be overridden via flags or env vars)
### ---------------------------------------------------------------------------
PROJECT_DIR="${PROJECT_DIR:-$HOME/dev/vm-vision-system-python}"
VENV_DIR_DEFAULT="$PROJECT_DIR/.venv"
SRC_DIR="${SRC_DIR:-$HOME/src}"
OPENCV_VERSION="${OPENCV_VERSION:-4.10.0}"
JOBS="${JOBS:-$(nproc)}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
CMAKE_GENERATOR="${CMAKE_GENERATOR:-Ninja}"

### Flags
FORCE=false           # proceed even if python/jupyter are running
CLEAN_ONLY=false      # just clean OpenCV from venv and exit
VENV_DIR="$VENV_DIR_DEFAULT"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --project-dir DIR         Project directory (default: $PROJECT_DIR)
  --venv-dir DIR            Virtualenv directory (default: $VENV_DIR_DEFAULT)
  --src-dir DIR             Source checkout directory (default: $SRC_DIR)
  --opencv-version VER      OpenCV version tag/branch (default: $OPENCV_VERSION)
  --jobs N                  Parallel build jobs for ninja (default: $(nproc))
  --force                   Continue even if python/ipython/jupyter are running
  --clean-only              Only remove OpenCV from venv, then exit
  -h, --help                Show this help

Env overrides (same names): PROJECT_DIR, SRC_DIR, OPENCV_VERSION, JOBS, BUILD_TYPE, CMAKE_GENERATOR
USAGE
}

### Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) PROJECT_DIR="$2"; shift 2;;
    --venv-dir) VENV_DIR="$2"; shift 2;;
    --src-dir) SRC_DIR="$2"; shift 2;;
    --opencv-version) OPENCV_VERSION="$2"; shift 2;;
    --jobs) JOBS="$2"; shift 2;;
    --force) FORCE=true; shift;;
    --clean-only) CLEAN_ONLY=true; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1"; usage; exit 2;;
  esac
done

VENV_DIR="${VENV_DIR:-$VENV_DIR_DEFAULT}"

### ---------------------------------------------------------------------------
### Helpers
### ---------------------------------------------------------------------------
log() { printf "\n\033[1;34m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\n\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err() { printf "\n\033[1;31m[ERR]\033[0m %s\n" "$*" >&2; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || { err "Missing command: $1"; exit 1; }; }

### ---------------------------------------------------------------------------
### 0) Ensure no Python processes are running (that might be using cv2)
### ---------------------------------------------------------------------------
check_running_python() {
  log "Checking for running Python/IPython/Jupyter processes…"
  if ps aux | grep -E "[p]ython|[i]python|[j]upyter" >/dev/null 2>&1; then
    warn "Detected running Python-like processes:"
    ps aux | grep -E "[p]ython|[i]python|[j]upyter" || true
    if [ "$FORCE" = false ]; then
      err "Please stop these processes or rerun with --force."
      exit 1
    else
      warn "--force specified; proceeding anyway."
    fi
  else
    log "No running Python/IPython/Jupyter processes found."
  fi
}

### ---------------------------------------------------------------------------
### 1) Ensure project dir & venv
### ---------------------------------------------------------------------------
ensure_project_and_venv() {
  if [ ! -d "$PROJECT_DIR" ]; then
    err "Project dir not found: $PROJECT_DIR"
    exit 1
  fi

  if [ ! -d "$VENV_DIR" ]; then
    log "Creating venv at $VENV_DIR …"
    require_cmd python3
    python3 -m venv "$VENV_DIR"
  fi

  log "Fixing ownership for venv (sudo may prompt)…"
  sudo chown -R "$USER":"$USER" "$VENV_DIR"

  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  log "Python: $(python -V 2>&1)"
  log "Using python: $(command -v python)"
  log "Using pip:    $(command -v pip)"
  python - <<'PY'
import sys
print("sys.prefix:", sys.prefix)
PY

  # Make sure pip/setuptools/wheel are recent
  python -m pip install --upgrade pip setuptools wheel >/dev/null
  # Ensure numpy exists for OpenCV build
  python -m pip install --upgrade numpy >/dev/null
}

### ---------------------------------------------------------------------------
### 2) Scrub OpenCV from venv
### ---------------------------------------------------------------------------
scrub_opencv_from_venv() {
  log "OpenCV packages present (before uninstall):"
  pip freeze | grep -i '^opencv' || echo "(none)"

  log "Uninstalling possible OpenCV wheels (ignoring missing)…"
  pip uninstall -y \
    opencv-python \
    opencv-contrib-python \
    opencv-python-headless \
    opencv-contrib-python-headless \
    opencv-python-inference-engine \
    opencv-contrib \
    opencv || true

  log "Removing leftover cv2/opencv artifacts from purelib & platlib…"
  PUREPKG=$(python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
  PLATPKG=$(python -c "import sysconfig;print(sysconfig.get_paths()['platlib'])")
  echo "purelib: $PUREPKG"
  echo "platlib: $PLATPKG"

  for SP in "$PUREPKG" "$PLATPKG"; do
    [ -d "$SP" ] || continue
    rm -rf \
      "$SP/cv2" \
      "$SP"/cv2.*.so \
      "$SP"/cv2*.so \
      "$SP"/cv2*.pyd \
      "$SP"/opencv* \
      "$SP"/opencv*dist-info \
      "$SP"/opencv*egg-info 2>/dev/null || true
  done

  log "Clearing pip cache…"
  pip cache purge || true

  log "Verifying cv2 is NOT importable…"
  if python - <<'PY'
try:
    import cv2  # noqa
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
  then
    err "cv2 is still importable in this venv."
    exit 1
  else
    log "✅ cv2 is NOT importable in this venv."
  fi

  log "OpenCV packages present (after cleanup):"
  pip freeze | grep -i '^opencv' || echo "(none)"
}

### ---------------------------------------------------------------------------
### 3) Install build tools & dev packages
### ---------------------------------------------------------------------------
install_build_deps() {
  require_cmd sudo
  log "Installing build dependencies via apt… (sudo may prompt)"
  sudo apt update
  sudo apt install -y \
    build-essential cmake ninja-build pkg-config git \
    python3-dev python3-numpy \
    libgtk-3-dev \
    libjpeg-dev libpng-dev libtiff-dev libwebp-dev \
    libopenexr-dev \
    libv4l-dev \
    libavcodec-dev libavformat-dev libswscale-dev libswresample-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-tools \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
}

### ---------------------------------------------------------------------------
### 4) Clone OpenCV + contrib
### ---------------------------------------------------------------------------
clone_opencv() {
  mkdir -p "$SRC_DIR"
  cd "$SRC_DIR"

  if [ ! -d opencv ]; then
    log "Cloning OpenCV $OPENCV_VERSION …"
    git clone --depth 1 --branch "$OPENCV_VERSION" https://github.com/opencv/opencv.git
  else
    log "opencv repo exists; ensuring correct version/tag…"
    (cd opencv && git fetch --depth 1 origin "$OPENCV_VERSION" && git checkout -f "$OPENCV_VERSION")
  fi

  if [ ! -d opencv_contrib ]; then
    log "Cloning opencv_contrib $OPENCV_VERSION …"
    git clone --depth 1 --branch "$OPENCV_VERSION" https://github.com/opencv/opencv_contrib.git
  else
    log "opencv_contrib repo exists; ensuring correct version/tag…"
    (cd opencv_contrib && git fetch --depth 1 origin "$OPENCV_VERSION" && git checkout -f "$OPENCV_VERSION")
  fi
}

### ---------------------------------------------------------------------------
### 5) Configure CMake
### ---------------------------------------------------------------------------
configure_build() {
  cd "$SRC_DIR/opencv"
  rm -rf build
  mkdir build
  cd build

  PY_INSTALL=$(python -c "import sysconfig; print(sysconfig.get_paths()['platlib'])")
  log "Python install path for cv2: $PY_INSTALL"

  cmake -G "$CMAKE_GENERATOR" \
    -D CMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -D CMAKE_INSTALL_PREFIX=/usr/local \
    -D OPENCV_EXTRA_MODULES_PATH="$SRC_DIR/opencv_contrib/modules" \
    -D OPENCV_GENERATE_PKGCONFIG=ON \
    -D BUILD_EXAMPLES=OFF \
    -D BUILD_TESTS=OFF \
    -D BUILD_DOCS=OFF \
    -D WITH_GSTREAMER=ON \
    -D WITH_FFMPEG=ON \
    -D WITH_V4L=ON \
    -D WITH_OPENGL=ON \
    -D BUILD_opencv_python3=ON \
    -D PYTHON3_EXECUTABLE="$(command -v python)" \
    -D OPENCV_PYTHON3_INSTALL_PATH="$PY_INSTALL" \
    ..
}

### ---------------------------------------------------------------------------
### 6) Build & install
### ---------------------------------------------------------------------------
build_and_install() {
  cd "$SRC_DIR/opencv/build"
  log "Building OpenCV with $JOBS jobs…"
  if [[ "$CMAKE_GENERATOR" =~ [Nn]inja ]]; then
    require_cmd ninja
    ninja -j"$JOBS"
    log "Installing (sudo may prompt)…"
    sudo ninja install
  else
    require_cmd make
    make -j"$JOBS"
    sudo make install
  fi
  log "Running ldconfig…"
  sudo ldconfig
}

### ---------------------------------------------------------------------------
### 7) Verify
### ---------------------------------------------------------------------------
verify_opencv() {
  log "Verifying OpenCV Python import and GStreamer support…"
  python - <<'PY'
import cv2, sys
print("cv2 version:", cv2.__version__)
print("cv2 path:", cv2.__file__)
bi = cv2.getBuildInformation()
# Quick check for GStreamer flag line
gst_line = next((ln for ln in bi.splitlines() if "GStreamer:" in ln), "")
print("GStreamer line:", gst_line)
if "GStreamer:" in gst_line and "YES" in gst_line:
    print("GStreamer enabled: YES")
else:
    print("GStreamer enabled: NO")
PY
}

### ---------------------------------------------------------------------------
### Main
### ---------------------------------------------------------------------------
main() {
  check_running_python
  ensure_project_and_venv
  scrub_opencv_from_venv

  if [ "$CLEAN_ONLY" = true ]; then
    log "--clean-only specified; stopping after cleanup."
    exit 0
  fi

  install_build_deps
  clone_opencv
  configure_build
  build_and_install
  verify_opencv

  log "✅ Done. OpenCV $OPENCV_VERSION is built from source, installed, and importable in your venv."
}

main "$@"
