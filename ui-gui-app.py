from PyQt5 import QtWidgets, uic
import sys
import os

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
        self.camnum.valueChanged.connect(self.apply_camera_settings)

        self.show()

    #def apply_camera_settings(self):
    #    # TODO - change camera settings using camera number and picture settings
    #    print("applying camera settings")
    
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

         # TODO - obstacle randomizations
         #      - one rumbles
         #      - two solid objects

         # TODO - mission site randomization (flip a coin)
         # TODO - draw OTV starting site (other side of coin)

        if self.showdest.isChecked():
            # TODO - draw destination in OpenCV
            print("drawing destination")

        if self.showobst.isChecked():
            # TODO - draw obstacles in OpenCV
            print("drawing obstacles")

        if self.showcoord.isChecked():
            # TODO - draw single coordinate in OpenCV
            print(f"drawing coordinate at ({self.xcoord.value()}, {self.ycoord.value()})")


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

app = QtWidgets.QApplication(sys.argv)
window = Ui()
app.exec_()
