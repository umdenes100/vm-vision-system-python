#!/bin/bash
sudo apt-get -y install v4l-utils
sudo apt install python3
sudo apt install python3-venv
sudo python3 -m venv .venv
sudo source .venv/bin/activate
sudo pip3 install -r requirements.txt

echo "Installation Complete"