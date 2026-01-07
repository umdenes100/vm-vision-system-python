# VM Vision System (Python)

A modular, headless vision system for an introductory robotics course.

## What it does (current + planned)

Current (implemented scaffolding):
- Receives a streamed video feed over UDP (current receiver assumes one JPEG frame per UDP datagram).
- Hosts a simple webpage showing the raw video feed (MJPEG stream).

Planned:
- Detects ArUco markers, crops the arena using markers 0–3, computes robot pose (X, Y, θ).
- Communicates pose + print messages with ESP-based clients using WebSocket.

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

1) Create and install into a virtual environment:
- cd install
- chmod +x install.sh
- ./install.sh

## Run

1) Start the system:
- cd core
- chmod +x run.sh
- ./run.sh

2) Open the webpage:
- http://<VM_IP>:8080/

## Configuration

Edit:
- core/config.json

### Notes on UDP video

The current UDP receiver expects each UDP datagram contains exactly one complete JPEG frame.

This is a simple and common approach for teaching systems. If your camera stream splits frames across multiple packets
(or uses RTP or another encoding), we will update the receiver to reassemble frames or support the correct format.

## Logging

Configured via core/config.json:
- DEBUG
- INFO
- WARN
- ERROR
- FATAL

Console format:
- [LEVEL] Message
