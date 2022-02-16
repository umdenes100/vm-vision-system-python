from PyQt5 import QtWidgets, QtGui, uic
import sys
import os
import math
from vs_opencv import *
import random
import time
from _thread import *

obstacle_presets = ['01A', '01B', '02A', '02B', '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B']

class Ui(QtWidgets.QMainWindow):
    def __init__(self, connections, dr_op):
        super(Ui, self).__init__()
        uic.loadUi('mainwindow.ui', self)
       
        # Apply Button
        #self.applybutton = self.findChild(QtWidgets.QPushButton, 'applybutton')
        #self.applybutton.clicked.connect(self.apply_camera_settings)

        # Randomize Button
        self.randomizebutton = self.findChild(QtWidgets.QPushButton, 'randomizebutton')
        self.randomizebutton.clicked.connect(self.randomize)

        # Reset Camera Button
        self.resetbutton = self.findChild(QtWidgets.QPushButton, 'resetbutton')
        self.resetbutton.clicked.connect(self.reset_camera)

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
        self.showobst = self.findChild(QtWidgets.QCheckBox, 'showobst')
        self.showcoord = self.findChild(QtWidgets.QCheckBox, 'showcoord')
        
        # Spin Boxes
        self.xcoord = self.findChild(QtWidgets.QDoubleSpinBox, 'xval')
        self.ycoord = self.findChild(QtWidgets.QDoubleSpinBox, 'yval')
        self.camnum = self.findChild(QtWidgets.QSpinBox, 'camnum')
        self.camnum.valueChanged.connect(self.camera_change)

        self.show()
        self.connections = connections
        self.dr_op = dr_op

    #def apply_camera_settings(self): # apply buttom may be removed
    #    # change camera settings using camera number and picture settings
    #    print("applying camera settings")
    
    def camera_change(self):
        start = time.time() 
        start_new_thread(self.connections.set_cam, (self.camnum.value(), ))
        #print(f"\nthis took {time.time() - start} seconds")
        print(f"camera changed to {self.camnum.value()}")

    def reset_camera(self):
        #print("resetting camera")
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

        # Update whether we need to draw destination, obstacles, and/or coordinates
        self.dr_op.draw_dest = self.showdest.isChecked()
        self.dr_op.draw_obstacles = self.showobst.isChecked()
        self.dr_op.draw_coordinate = self.showcoord.isChecked()

    def brightness(self):
        #print(f"brightness is now {self.brightslider.value()}")
        command = f'v4l2-ctl -d /dev/video{self.camnum.value()} -c brightness={self.brightslider.value()}'
        os.system(command)

    def sharpness(self):
        #print(f"sharpness is now {self.sharpslider.value()}")
        command = f'v4l2-ctl -d /dev/video{self.camnum.value()} -c sharpness={self.sharpslider.value()}'
        os.system(command)

    def contrast(self):
        #print(f"contrast is now {self.contrastslider.value()}")
        command = f'v4l2-ctl -d /dev/video{self.camnum.value()} -c contrast={self.contrastslider.value()}'
        os.system(command)

def start_gui(connections, dr_op):
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon('/var/lib/app-info/icons/ubuntu-focal-universe/64x64/gnome-video-arcade_gnome-video-arcade.png'))
    window = Ui(connections, dr_op)
    app.exec_()

