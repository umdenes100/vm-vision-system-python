import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

widgets = {"Checkboxes": [], "Sliders": [], "Buttons": [], "AbstractSliders": []}

'''
class SliderProxyStyle(QProxyStyle):
    def pixelMetric(self, metric, option, widget):
        if metric == QStyle.PM_SliderThickness:
            return 10
        elif metric == QStyle.PM_SliderLength:
            return 10
        elif metric == QStyle.sliderPositionFromValue:
            return 15, 300, 50, 300
        return super().pixelMetric(metric, option, widget)
'''


def window():
    app = QApplication(sys.argv)
    w = QWidget()

    # Window settings
    w.setGeometry(100,100,300,500) # window starts at [100, 100] and is 300x500
    w.setWindowTitle("Vision System 2.0")

    # Titles
    t1 = QLabel(w)
    t1.setText("Arena Settings")
    t1.move(7,12)
    
    t2 = QLabel(w)
    t2.setText("Camera Settings")
    t2.move(7,250)
    widgets["Buttons"] = [t1, t2]


    # checkboxes
    check1 = QCheckBox(w)
    check1.setText("Show Destination")
    check1.move(15,40)
    
    check2 = QCheckBox(w)
    check2.setText("Show Obstacles")
    check2.move(15,70)
    
    check3 = QCheckBox(w)
    check3.setText("Show Custom Coordinate:")
    check3.move(15,100)

    # sliders
    sl1 = QSlider(Qt.Horizontal, w)
    sl1.setMinimum(0)
    sl1.setMaximum(255)
    sl1.setValue(127)
    sl1.setStyle(SliderProxyStyle(sl1.style()))
    sl1.move(15, 300)

    sl2 = QSlider(Qt.Horizontal, w)
    sl2.setMinimum(0)
    sl2.setMaximum(255)
    sl2.setValue(127)
    sl2.move(15, 350)

    sl3 = QSlider(Qt.Horizontal, w)
    sl3.setMinimum(0)
    sl3.setMaximum(255)
    sl3.setValue(127)
    sl3.move(15, 400)


    # abstract sliders

    #win = QDialog()
    b1 = QPushButton(w)
    b1.setText("Randomize")
    b1.move(150,200)
    b1.clicked.connect(b1_clicked)
   
    b2 = QPushButton(w)
    b2.setText("Reset Camera")
    b2.move(150,450)
    b2.clicked.connect(b2_clicked)

    w.show()
    #win.show()
    sys.exit(app.exec_())


def b1_clicked():
    print("Randomized button clicked")

def b2_clicked():
    print("Camera reset button clicked")

if __name__ == '__main__':
    window()
