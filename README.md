# VM Vision System (Python)

A modular, headless vision system for an introductory robotics course.

## What it does (current + planned)
- **Receives** a streamed video feed over **UDP** (current scaffolding assumes one JPEG frame per datagram).
- **Hosts** a simple webpage showing the **raw video feed** (MJPEG stream).
- (Planned) Detects ArUco markers, crops arena using markers 0–3, computes robot pose (X, Y, θ).
- (Planned) Communicates pose + print messages with ESP-based clients using **WebSocket**.


## Install
```bash
cd install
chmod +x install.sh
./install.sh

