# Vision System Notes

## OpenCV
To install **OpenCV**:
```
$ sudo apt-get install python3-opencv
```
OpenCv also needs **Numpy** as a dependency for many of its functions.
```
$ sudo apt install python3-numpy
```
### Capturing Images and Capturing ArUco Markers
The below code is used to capture, process, and draw ArUco Markers
```python
arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_1000)
arucoParams = cv2.aruco.DetectorParameters_create()
(corners, ids, rejected) = cv2.aruco.detectMarkers(frame, arucoDict, parameters=arucoParams)
frame = cv2.aruco.drawDetectedMarkers(frame,corners,ids)
```
- ```python cv2.aruco.DICT_4X4_1000``` can be replaced with any type of ArUco Marker dictionary
### Arena Transformation
The OpenCV portion of the Vision system relies on matrix transformations in order to convert between the pixel coordinates and our arena coordinates. The functions shown below are used to convert pixel coordinates to arena coordinates and vice versa. 

```python
cv2.getPerspectiveTransform(src_pts, dst_pts)
```
- **src_pts** and **dst_pts** are Numpy float arrays containing the respective coordinates.
- **src_pts** will contain the pixel coordinates of each corner of the Aruco Markers 0-3
- **dst_pts** will contain the arena coordinates that we define
- The function will return a 3-D Numpy Array, which will be used later to convert between pixel coordinates and our customized coordinates

```python
cv2.perspectiveTransform(point1, matrix)
```
- **matrix**: This will either be the H matrix or the inverse of the H matrix depending on what we want to do. 
  - Use the H matrix to convert pixel coordinates to arena coordinates 
  - Use the inverse of the H matrix to convert arena coordinates to pixel coordinates
- **point1**: A numpy 3-D array which will contain the coordinates we want to convert

### Drawing Functions

The following functions will be used in order to draw out various shapes, and put text on the image 

There are some common parameters we will see across various functions. They are:
- color: An integer tuple with the form (Green, Blue, Red)
- thickness: Integer which controls how thick the shape will be in pixels. 
  - Setting thickness to ```-1``` will fill in the shape which is drawn

```python 
cv2.arrowedLine(frame,start_point, end_point, color, thickness, tipLength)
```
- start_point: An integer tuple of the form (x,y) which is where the arrowed line will start
- end_point: An integer tuple of the form(x,y) which is where the "tip" of the arrow will be
- tipLength: Can be a float. Controls how long the ends of the arrow will be


```python 
cv2.rectangle(frame,start_point, end_point,color,thickness)
```
- start_point: An integer tuple of the form (x,y) which is the bottom left corner of the rectangle
- end_point: An integer tuple of the form(x,y) which is where the "tip" of the arrow will be

```python 
cv2.circle(frame,center,radius,color,thickness)
```
- center: An integer tuple of the form (x,y) which is the center point of the circle
- radius: An integer which represents the radius of the circle
```python 
cv2.putText(frame, text, start_point, font, 1, color, thickness, cv2.LINE_AA) 
```
- text: String which contains the text to be put on the string
- start_point: An integer tuple of the form (x,y) which is the bottom left corner of where the text will be drawn
- font: Font type for the text. We use 
```python 
-cv2.FONT_HERSHEY_SIMPLEX
```
              
[RGB Color Picker](https://www.rapidtables.com/web/color/RGB_Color.html)
https://codeyarns.com/tech/2015-03-11-fonts-in-opencv.html
## Websockets
TODO - notes on python3 websockets

## PyQt5
To install **Qt 5 Designer**:
```
$ sudo apt-get install qttools5-dev-tools
$ sudo apt-get install qttools5-dev
```
If you're wondering what Qt 5 Creator is, this is the same thing as Qt 5 Designer, but for C/C++ 
programs using Qt5.

This is the `start_gui()` method called in **vs_main.py**
```python
def start_gui(connections, dr_op):
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon('/snap/gtk-common-themes/1519/share/icons/elementary-xfce/categories/48/applications-arcade.png'))
    window = Ui(connections, dr_op)
    app.exec_()
```

The window icon isn't required, but it's a nice touch so that we know which application is
popping up in our dock. The dr_op is just a class of data that will be used in the UI class.

Here is an example of the *Brightness Slider* used in the Vision System GUI:
```python
# Brightness Slider
self.brightslider = self.findChild(QtWidgets.QSlider, 'brightslider')
self.brightslider.sliderReleased.connect(self.brightness)

...

def brightness(self):
    command = f'v4l2-ctl -d /dev/video{self.connections.camnum} -c brightness={self.brightslider.value()}'
    os.system(command)
```

We create a slider object in the UI class and find it via it's name, which can be set in Qt 5 Designer by 
right-clicking on the object and changing the objectName. We then define a function for the slider and 
attach the *brightness* function to the Qt trigger for when the slider is *released*. In this case, we 
will change the brightness of the current camera to the current slider value by using **v4l2-ctl**.

This is just an example of an actionable item represented in Python with certain actions.

[QtWidgets](https://doc.qt.io/qtforpython/PySide6/QtWidgets/index.html#module-PySide6.QtWidgets)

[A nice tutorial on PyQt5](https://www.blog.pythonlibrary.org/2021/09/29/create-gui/)

[Another nice tutorial](https://nitratine.net/blog/post/how-to-import-a-pyqt5-ui-file-in-a-python-gui/)

[Tutorialspoint](https://www.tutorialspoint.com/pyqt5/pyqt5_introduction.htm)


## Lab PCs
The Lab PCs that ran teh C++ version of the Vision System currently exist in the dungeon
and contain Ubuntu 16.04 as its OS. The new PCs that are currently hanging up and used for
this Python3 Vision System runs Ubuntu 20.04.


### v4l2-ctl
**v4l2-ctl** is a native Linux tool to control devices like cameras, radio, swradio, etc. I 
struggled for the *longest* time trying to mess with these settings on Ubuntu for the Vision 
System. It is my assumption that these settings are either written over or ignored when opening 
the Vision System webcam up in OpenCV. I haven't found a solution for using the v4l2-ctl utility
with OpenCV in python. 

The solution, in the end, was to add an extra argument to `cv2.VideoCapture()` in Python, which
is explained more above. General note: don't try to use **v4l2-ctl** with the Vision System for your 
own sanity.

We do, however, use **v4l2-ctl** for changing camera settings like changing the brightness, contrast, 
and sharpness. 

TODO - add links

### usb_reset.py
This is a short program that can be ran from the Desktop on the Lab PCs that 
refreshes the current cameras plugged in through USB. This has only been tested
for the Besteker and Logitech cameras. Run this program (requires root password)
if the cameras are **plugged in** and **not showing up** on the Vision System or 
when running `ls /dev/video*` in terminal.

## WiFi firmware setup
The IP address for the Vision System PC is hardcoded in firmware for the WiFi 
(ESP8266) Module. As of now, it is set to `192.168.1.2` in both labs. In order 
to make this happen, one must set DHCP to manual and set the following values:

- IP Address: `192.168.1.2`
- Subnet: `255.255.255.0`
- Gateway: `192.168.1.1`
- DNS (optional): `8.8.8.8` or `8.8.4.4`

If you would like to change the IP address for the communication from/to the WiFi modules, 
you must change the manual DHCP settings and the firmware for each WiFi module that will be 
connecting to that system.
