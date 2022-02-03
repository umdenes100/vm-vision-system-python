from PyQt5 import QtWidgets, uic
import sys
import os
import math
import vs_opencv

obstacle_presets = ['01A', '01B', '02A', '02B', '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B']
camera_num = 0

class Ui(QtWidgets.QMainWindow):
    def __init__(self):
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

    #def apply_camera_settings(self): # apply buttom may be removed
    #    # change camera settings using camera number and picture settings
    #    print("applying camera settings")
    
    def camera_change(self):
        camera_num = self.camnum.value()
        print(f"camera changed to {camera_num}")

    def reset_camera(self):
        print("resetting camera")
        self.brightslider.setValue(127)
        self.sharpslider.setValue(127)
        self.contrastslider.setValue(127)
        self.brightness()
        self.sharpness()
        self.contrast()

    def randomize(self):
        print("randomizing")

        # obstacle randomization, then pass onto opencv
        #   - one rumbles
        #   - two solid objects
        vs_opencv.drawing_options['randomization'] = obstacle_presets[random.randrange(0,12)]
        
        # otv start location and mission location
        start = random.randrange(0,2)
        vs_opencv.drawing_options['otv_start_loc'] = start
        vs_opencv.drawing_options['mission_loc'] = (start + 1) % 2 # opposite of OTV start
        
        # otv start direction (theta) (always facing away from mission site inn 180 deg span)
        if start == 0: # BOTTOM
            vs_opencv.drawing_options['otv_start_dir_theta'] = (random.randrange(0,180) * 2 * math.pi) / 360 
        else:
            vs_opencv.drawing_options['otv_start_dir_theta'] = ((random.randrange(0,180) +180) * 2 * math.pi) / 360

        # Update whether we need to draw destination, obstacles, and/or coordinates
        vs_opencv.drawing_options['draw_dest'] = self.showdest.isChecked()
        vs_opencv.drawing_options['draw_obstacles'] = self.showobst.isChecked()
        vs_opencv.drawing_options['draw_coord'] = self.showcoord.isChecked()

    def brightness(self):
        print(f"brightness is now {self.brightslider.value()}")
        command = f'v412-ctl -d /dev/video{self.camnum.value()} -c brightness={self.brightslider.value()}'
        os.system(command)

    def sharpness(self):
        print(f"sharpness is now {self.sharpslider.value()}")
        command = f'v412-ctl -d /dev/video{self.camnum.value()} -c sharpness={self.sharpslider.value()}'
        os.system(command)

    def contrast(self):
        print(f"contrast is now {self.contrastslider.value()}")
        command = f'v412-ctl -d /dev/video{self.camnum.value()} -c contrast={self.contrastslider.value()}'
        os.system(command)

def start_gui():
    app = QtWidgets.QApplication(sys.argv)
    window = Ui()
    app.exec_()

