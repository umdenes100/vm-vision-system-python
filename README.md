# VM Vision System (Python)

A modular, headless vision system for an introductory robotics course.

## What it does (current + planned)

Current:
- Receives a streamed video feed over UDP as RTP/H.264 (from a Raspberry Pi sender).
- Decodes the RTP/H.264 stream into JPEG frames using GStreamer on the VM.
- Hosts a simple webpage showing the raw video feed as MJPEG.

Planned:
- Detect ArUco markers.
- Crop the arena using markers 0–3.
- Compute robot pose (X, Y, theta).
- Communicate with ESP-based clients using WebSocket.

## Repo layout

vm-vision-system-python/
  .gitignore
  README.md
  communications/
    arenacam.py
  frontend/
    webpage.py
  core/
    main.py
    run.sh
    config.json
  install/
    requirements.txt
    install.sh
  utils/
    logging.py

## Install

Python dependencies:

cd install
chmod +x install.sh
./install.sh

System requirement (VM):
- GStreamer must be installed and able to decode H.264.

Typical Ubuntu/Debian packages (install via apt):
- gstreamer1.0-tools
- gstreamer1.0-plugins-base
- gstreamer1.0-plugins-good
- gstreamer1.0-plugins-bad
- gstreamer1.0-plugins-ugly
- gstreamer1.0-libav

## Run

cd core
chmod +x run.sh
./run.sh

Then open:
http://<VM_IP>:8080/

## Configuration

Edit:
core/config.json

## Camera sender (Raspberry Pi 5)

Your sender is producing RTP/H.264 over UDP, for example:

rpicam-vid ... --codec h264 ... -o - | \
gst-launch-1.0 fdsrc ! h264parse ! rtph264pay config-interval=1 pt=96 ! \
  udpsink host=<VM_IP> port=5000

This project expects that exact transport:
- UDP port matches core/config.json
- RTP payload type matches core/config.json (default 96)

## Logging

Configured via core/config.json:

DEBUG
INFO
WARN
ERROR
FATAL

Console format:
[LEVEL] Message
