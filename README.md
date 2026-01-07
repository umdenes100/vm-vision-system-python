# VM Vision System (Python)

A modular, headless vision system for an introductory robotics course.

## What it does (current)
- Receives a streamed video feed over UDP as RTP/H.264 (from a Raspberry Pi sender).
- Decodes the RTP/H.264 stream into JPEG frames using GStreamer on the VM.
- Detects ArUco markers, draws green marker boxes.
- Crops the arena using corner markers (0–3) and outputs a stabilized cropped stream.
- Hosts a web UI:
  - Static frontend assets (HTML/CSS/JS) served from `frontend/static/`
  - Dynamic endpoints (streams, placeholder WS/API) handled in `frontend/webpage.py`

## Repo layout

vm-vision-system-python/
  .gitignore
  README.md
  communications/
    arenacam.py
  vision/
    aruco.py
    arena.py
  frontend/
    webpage.py
    static/
      index.html
      bootstrap.css
      header.css
      index.css
      inputs.css
      theme.css
      ui-config.js
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

cd core  
./run.sh  

Open:
http://<VM_IP>:8080/

## Endpoints
- `/` : static UI (currently placeholders + center crop stream)
- `/crop` : cropped arena (with ArUco boxes)
- `/overlay` : raw feed with ArUco boxes
- `/video` : raw feed
- `/ws` : placeholder WebSocket endpoint (future UI interactions)
