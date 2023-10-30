#!/bin/bash
# These you would run yourself. YOU MUST INSTALL IN THE HOME DIRECTORY!
#sudo git clone https://github.com/umdenes100/Vision-System-Python.git
#cd Vision-System-Python
sudo apt-get update
sudo apt-get -y install v4l-utils
sudo apt install python3
sudo apt install python3-pip
sudo apt install python3-venv
# make a virtual environment
sudo python3 -m venv .venv
# activate the virtual environment
source .venv/bin/activate
# install the requirements
sudo .venv/bin/pip3 install -r requirements.txt
# Copy the desktop icon to the desktop
cp runner.desktop ~/Desktop/runner.desktop
# Enable execution of the runner script.
sudo chmod +x RunVisionSystem.sh

echo "Installation Script Complete - please follow up with the following steps:"
echo "1. Configure the network as per the README - (make sure to set the static ip of this machine to 192.168.1.2)"
echo "2. Right click the desktop icon and select 'Allow Launching' to enable the desktop shortcut."