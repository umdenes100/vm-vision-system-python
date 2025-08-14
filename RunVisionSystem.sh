#!/usr/bin/env bash

# i) Supress Qt Debugging
export QT_LOGGING_RULES="*.debug=false"

cd ~/Vision-System-Python

# 1) Load NVM so we can use the right Node version:
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use default    # your default is v18.20.8

# 2) For headless (no real display), use Qt offscreen:
export QT_QPA_PLATFORM=offscreen

# 3) Start your Node listener:
node components/machinelearning/listen.mjs >/dev/null &

# 4) Activate Python virtualenv and launch:
source .venv/bin/activate
python3 main.py --no_gui #2>/dev/null
# 2>/dev/null supresses certain errors (like Qt and Gstreamer).
