import logging
import threading

from PyQt5 import QtWidgets, QtGui, uic
import sys
import os
import math

from data import dr_op, camera
import random
import subprocess

gui_is_running = True


class Ui(QtWidgets.QMainWindow):
    def __init__(self):
        super(Ui, self).__init__()
        uic.loadUi('mainwindow.ui', self)
        import signal

        signal.signal(signal.SIGINT, signal.SIG_DFL)

        # Randomize Button
        self.randomize_button = self.findChild(QtWidgets.QPushButton, 'randomize_button')
        self.randomize_button.clicked.connect(self.randomize)

        # Reset Camera Button
        self.reset_button = self.findChild(QtWidgets.QPushButton, 'reset_button')
        self.reset_button.clicked.connect(self.reset_camera)

        # Text box for camera
        self.cam_list = self.findChild(QtWidgets.QListWidget, 'camList')
        self.cam_list.itemClicked.connect(self.camera_change)

        # ... find valid camera numbers to display
        cameras = os.listdir('/dev/')
        cameras.sort()
        for c in cameras:
            if "video" in c:
                process = subprocess.Popen(['v4l2-ctl', f'--device=/dev/{c}', '--all'], stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                out, err = process.communicate()
                if b"Format Video Capture:" in out:
                    self.cam_list.addItem(c)

        # Brightness Slider
        self.bright_slider = self.findChild(QtWidgets.QSlider, 'bright_slider')
        self.bright_slider.sliderReleased.connect(self.brightness)

        # Sharpness Slider
        self.sharp_slider = self.findChild(QtWidgets.QSlider, 'sharp_slider')
        self.sharp_slider.sliderReleased.connect(self.sharpness)

        # Focus Slider
        self.contrast_slider = self.findChild(QtWidgets.QSlider, 'contrast_slider')
        self.contrast_slider.sliderReleased.connect(self.contrast)

        # Checkboxes
        self.showdest = self.findChild(QtWidgets.QCheckBox, 'showdest')
        self.showdest.stateChanged.connect(self.show_dest)
        self.showobst = self.findChild(QtWidgets.QCheckBox, 'showobst')
        self.showobst.stateChanged.connect(self.show_obst)
        logging.debug("GUI initialized")
        self.show()
        logging.debug("GUI shown")

    def camera_change(self, item):
        camnum = int(str(item.text()).strip()[-1])
        camera.set_cam(camnum)
        print(f"camera changed to {camnum}")

    def reset_camera(self):
        self.bright_slider.setValue(127)
        self.sharp_slider.setValue(127)
        self.contrast_slider.setValue(127)
        self.brightness()
        self.sharpness()
        self.contrast()

    def randomize(self):
        # obstacle randomization, then pass onto opencv
        #   - one rumbles
        #   - two solid objects
        dr_op.randomization = dr_op.obstacle_presets[random.randrange(0, 12)]

        # otv start location and mission location
        if dr_op.randomization[:2] == '01' or dr_op.randomization[:2] == '10':
            start = 1
        elif dr_op.randomization[:2] == '21' or dr_op.randomization[:2] == '12':
            start = 0
        else:
            start = random.randrange(0, 2)
        dr_op.otv_start_loc = start
        dr_op.mission_loc = (start + 1) % 2  # opposite of OTV start

        # otv start direction (theta) (always facing away from mission site inn 180 deg span)
        if start == 0:  # BOTTOM
            dr_op.otv_start_dir = (random.randrange(0, 180) * 2 * math.pi) / 360
        else:
            dr_op.otv_start_dir = ((random.randrange(0, 180) + 180) * 2 * math.pi) / 360

    def show_dest(self):
        dr_op.draw_dest = self.showdest.isChecked()

    def show_obst(self):
        dr_op.draw_obstacles = self.showobst.isChecked()

    def brightness(self):
        command = f'v4l2-ctl -d /dev/video{camera.camera_num} -c brightness={self.bright_slider.value()}'
        logging.debug(command)
        os.system(command)

    def sharpness(self):
        command = f'v4l2-ctl -d /dev/video{camera.camera_num} -c sharpness={self.sharp_slider.value()}'
        os.system(command)

    def contrast(self):
        command = f'v4l2-ctl -d /dev/video{camera.camera_num} -c contrast={self.contrast_slider.value()}'
        os.system(command)


def start_gui():
    global gui_is_running
    gui_is_running = True
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(
        QtGui.QIcon('/snap/gtk-common-themes/1519/share/icons/elementary-xfce/categories/48/applications-arcade.png'))
    window = Ui()
    window.show()
    logging.debug("doing exec")
    sys.exit(app.exec())
