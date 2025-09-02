1) Fix permissions in your venv & uninstall the wheel
```bash
# Make sure NO Python process is using cv2
ps aux | grep -E "python|ipython|jupyter"

# Adjust this path if your venv path is different:
VENV_DIR="$HOME/vm-vision-system-python/.venv"

# Fix ownership so your user can edit files inside the venv
sudo chown -R "$USER":"$USER" "$VENV_DIR"

# Now uninstall any OpenCV wheels cleanly
source "$VENV_DIR/bin/activate"
pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless

# If anything still remains, remove it manually
SITEPKG=$(python -c "import sysconfig;print(sysconfig.get_paths()['platlib'])")
rm -rf "$SITEPKG/cv2" "$SITEPKG/opencv*"
```

2) Install missing build tools & correct dev packages
```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build pkg-config git \
  python3-dev python3-numpy \
  libgtk-3-dev \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev \
  libopenexr-dev \
  libv4l-dev \
  libavcodec-dev libavformat-dev libswscale-dev libswresample-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-tools \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
```

3) Configure a fresh OpenCV build (with your venv active)
```bash
# If you haven’t cloned yet, do this first:
# mkdir -p ~/src && cd ~/src
# git clone --depth 1 --branch 4.10.0 https://github.com/opencv/opencv.git
# git clone --depth 1 --branch 4.10.0 https://github.com/opencv/opencv_contrib.git

cd ~/src/opencv
rm -rf build && mkdir build && cd build

PY_INSTALL=$(python -c "import sysconfig; print(sysconfig.get_paths()['platlib'])")
echo "Installing cv2 to: $PY_INSTALL"

cmake -G Ninja \
  -D CMAKE_BUILD_TYPE=Release \
  -D CMAKE_INSTALL_PREFIX=/usr/local \
  -D OPENCV_EXTRA_MODULES_PATH=~/src/opencv_contrib/modules \
  -D OPENCV_GENERATE_PKGCONFIG=ON \
  -D BUILD_EXAMPLES=OFF -D BUILD_TESTS=OFF -D BUILD_DOCS=OFF \
  -D WITH_GSTREAMER=ON -D WITH_FFMPEG=ON -D WITH_V4L=ON -D WITH_OPENGL=ON \
  -D BUILD_opencv_python3=ON \
  -D PYTHON3_EXECUTABLE="$(which python)" \
  -D OPENCV_PYTHON3_INSTALL_PATH="$PY_INSTALL" \
  ..
```

4) Build & install
```bash
ninja -j"$(nproc)"
sudo ninja install
sudo ldconfig
```

5) Verify you’re using the source build and GStreamer is ON
```bash
python - << 'PY'
import cv2
print("cv2:", cv2.__version__)
print("Using:", cv2.__file__)
print("GStreamer enabled? ->", "YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "NO")
PY
