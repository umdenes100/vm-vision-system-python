# VM Vision System (Python)

A modular, headless vision system for an introductory robotics course.

---

## Overview

This system runs on a headless Linux VM and provides:

- UDP ingestion of an RTP/H.264 camera stream (e.g., from a Raspberry Pi)
- ArUco marker detection and arena cropping
- A web-based UI for visualization and team monitoring
- WebSocket communication with ESP-based robots
- A machine learning model listener that syncs student models from Firebase

---

## Repository Layout

vm-vision-system-python/  
├── .gitignore  
├── README.md  
├── communications/  
│   ├── arenacam.py  
│   └── wifi_server.py  
├── vision/  
│   ├── aruco.py  
│   └── arena.py  
├── machinelearning/  
│   ├── listener.py  
│   └── models/  
├── frontend/  
│   ├── webpage.py  
│   └── static/  
│       ├── index.html  
│       ├── bootstrap.css  
│       ├── header.css  
│       ├── index.css  
│       ├── inputs.css  
│       ├── theme.css  
│       ├── uiconfig.js  
│       └── ui-config.json  
├── core/  
│   ├── main.py  
│   ├── run.sh  
│   └── config.json  
├── install/  
│   ├── install.sh  
│   └── requirements.txt  
└── utils/  
    ├── logging.py  
    └── port_guard.py  

---

## Core Features

Camera & Vision
- Receives RTP/H.264 video over UDP
- Decodes frames using GStreamer
- Detects all ArUco markers
- Uses markers 0–3 to define the arena
- Crops the arena and outputs a stabilized stream

Web Interface
- Static frontend served from frontend/static
- Dynamic backend via frontend/webpage.py

ESP Communication
- WebSocket server on port 7755
- begin / print / ping / aruco ops supported

Machine Learning Listener
- Mirrors legacy Firebase-based model sync
- Downloads models into machinelearning/models
- Started and stopped automatically by core/main.py

---

## Running

cd core
./run.sh

Open:
http://<VM_IP>:8080/
