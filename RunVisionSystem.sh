cd ~/Vision-System-Python
export QT_QPA_PLATFORM=wayland
~/.nvm/versions/node/v18.20.4/bin/node ~/Vision-System-Python/components/machinelearning/listen.mjs >/dev/null &

~/Vision-System-Python/.venv/bin/python3 ~/Vision-System-Python/main.py
