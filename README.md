# VM Vision System (Python)

A modular, headless vision system for an introductory robotics course.

## What it does (current)
- Receives a streamed video feed over UDP as RTP/H.264 (from a Raspberry Pi sender).
- Decodes the RTP/H.264 stream into JPEG frames using GStreamer on the VM.
- Detects ArUco markers, draws marker boxes.
- Crops the arena using corner markers (0–3) and outputs a stabilized cropped stream.
- Hosts a web UI:
  - Static frontend assets (HTML/CSS/JS) served from `frontend/static/`
  - Dynamic endpoints (streams, placeholder WS/API) handled in `frontend/webpage.py`
- Hosts an ESP WebSocket server for team connections and messaging.

## Repo layout

vm-vision-system-python/
  .gitignore
  README.md
  communications/
    arenacam.py
    wifi_server.py
  vision/
    aruco.py
    arena.py
  machinelearning/
    listener.py
    models/
  frontend/
    webpage.py
    static/
      index.html
      bootstrap.css
      header.css
      index.css
      inputs.css
      theme.css
      uiconfig.js
      ui-config.json
  core/
    main.py
    run.sh
    config.json
  install/
    requirements.txt
    install.sh
  utils/
    logging.py
    port_guard.py

## Run

```bash
cd core
./run.sh
