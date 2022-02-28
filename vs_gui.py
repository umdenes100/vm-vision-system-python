from PyQt5 import QtWidgets, QtGui, uic
import sys
import os
import math
from vs_opencv import *
import random
import time
from _thread import *
import subprocess

obstacle_presets = ['01A', '01B', '02A', '02B', '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B']

class Ui(QtWidgets.QMainWindow):
    def __init__(self, connections, dr_op):
        super(Ui, self).__init__()
        uic.loadUi('mainwindow.ui', self)
       
        # Randomize Button
        self.randomizebutton = self.findChild(QtWidgets.QPushButton, 'randomizebutton')
        self.randomizebutton.clicked.connect(self.randomize)

        # Reset Camera Button
        self.resetbutton = self.findChild(QtWidgets.QPushButton, 'resetbutton')
        self.resetbutton.clicked.connect(self.reset_camera)

        # Text box for camera
        self.camlist = self.findChild(QtWidgets.QListWidget, 'camList')
        self.camlist.itemDoubleClicked.connect(self.camera_change)
        
        # ... find valid camera numbers to display
        cameras = os.listdir('/dev/')
        cameras.sort()
        for c in cameras:
            if "video" in c:
                process = subprocess.Popen(['v4l2-ctl', f'--device=/dev/{c}', '--all'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = process.communicate()
                if b"Format Video Capture:" in out:
                    self.camlist.addItem(c)

        # Brightness Slider
        self.brightslider = self.findChild(QtWidgets.QSlider, 'brightslider')
        self.brightslider.sliderReleased.connect(self.brightness)

        # Sharpness Slider
        self.sharpslider = self.findChild(QtWidgets.QSlider, 'sharpslider')
        self.sharpslider.sliderReleased.connect(self.sharpness)

        # Focus Slider
        self.contrastslider = self.findChild(QtWidgets.QSlider, 'contrastslider')
        self.contrastslider.sliderReleased.connect(self.contrast)

        # Checkboxes
        self.showdest = self.findChild(QtWidgets.QCheckBox, 'showdest')
        self.showdest.stateChanged.connect(self.show_dest)
        self.showobst = self.findChild(QtWidgets.QCheckBox, 'showobst')
        self.showobst.stateChanged.connect(self.show_obst)

        self.show()
        self.connections = connections
        self.dr_op = dr_op

    def camera_change(self, item):
        camnum = int(str(item.text()).strip()[-1])
        start_new_thread(self.connections.set_cam, (camnum, ))
        #print(f"camera changed to {camnum}")

    def reset_camera(self):
        self.brightslider.setValue(127)
        self.sharpslider.setValue(127)
        self.contrastslider.setValue(127)
        self.brightness()
        self.sharpness()
        self.contrast()

    def randomize(self):
        # obstacle randomization, then pass onto opencv
        #   - one rumbles
        #   - two solid objects
        self.dr_op.randomization = obstacle_presets[random.randrange(0,12)]
        
        # otv start location and mission location
        start = random.randrange(0,2)
        self.dr_op.otv_start_loc = start
        self.dr_op.mission_loc = (start + 1) % 2 # opposite of OTV start
        
        # otv start direction (theta) (always facing away from mission site inn 180 deg span)
        if start == 0: # BOTTOM
            self.dr_op.otv_start_dir = (random.randrange(0,180) * 2 * math.pi) / 360 
        else:
            self.dr_op.otv_start_dir = ((random.randrange(0,180) +180) * 2 * math.pi) / 360

    def show_dest(self):
        self.dr_op.draw_dest = self.showdest.isChecked()

    def show_obst(self):
        self.dr_op.draw_obstacles = self.showobst.isChecked()

    def brightness(self):
        command = f'v4l2-ctl -d /dev/video{self.connections.camnum} -c brightness={self.brightslider.value()}'
        os.system(command)

    def sharpness(self):
        command = f'v4l2-ctl -d /dev/video{self.connections.camnum} -c sharpness={self.sharpslider.value()}'
        os.system(command)

    def contrast(self):
        command = f'v4l2-ctl -d /dev/video{self.connections.camnum} -c contrast={self.contrastslider.value()}'
        os.system(command)

def start_gui(connections, dr_op):
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon('/snap/gtk-common-themes/1519/share/icons/elementary-xfce/categories/48/applications-arcade.png'))
    window = Ui(connections, dr_op)
    app.exec_()

