# Vision-System-Python
A new vision system written in Python. The devlopment of this Vision System is heavily based on
the prior versions of the Vision System, which were written in C++.

## Communcation
This is the "server-side" application for the vision system that communicates with both the 
[front-end application](https://github.com/umdenes100/VisionSystemRemoteClient) and the 
[WiFi Modules (ESP8266)](https://github.com/umdenes100/WifiFirmware).

### Front-end Communcation
The front-end communication works over **TCP 8080** and **TCP 9000**. 

The *image server* is the connection over TCP port 8080 and serves the JPEG images coming 
from the video feed. The front-end handles these images and displays them when a user 
is connected properly. This connection is a one-way connection, meaning the back-end is
not expecting any communication *back* over port 8080.

The *message server* is the connection over TCP port 9000 and acts as the message communication
back and forth between the front-end and this back-end. This is a two-way communication channel
where the back-end will send things like debug messages and mission calls to the front-end and 
the front-end will send other pieces of information back. 

### WiFi Communication
The OTV uses the ESP8266 modules to communicate over UDP port 7755. Check out the reference
at the bottom of this README if you don't know the difference between TCP and UDP communication.

The structure of the packets are the following:
```
[seq_byte][func_call][message]
```

**Function Calls:**
- 0 = PING
- 2 = Enes100.begin()
- 4 = Enes100.updateLocation()
- 6 = Enes100.mission()
- 8 = Enes100.print() or Enes100.println() 

*NOTE: the sequence numbers are not really used*

## Files
The important files will be listed and summed up below.

### vs_main.py

### vs_gui.py
This program includes the functionality behind the GUI for the main window, using **mainwindow.ui**
as tghe design file for the GUI. The changes on the gui are passed as system commands to change 
camera settings or passed to a data structure for drawing settings for **vs_opencv.py** to use.

### vs_opencv.py
This includes capturing camera frames and passing them to the image server. This is where
the drawings for the video feed are updated using one data structure that **vs_gui.py** 
writes to when switches on the GUI menu are changed.

### vs_mission.py
This contains one big function to return the correct response when a mission() call was called
over UDP 7755.

### mainwindow.ui
This is the GUI interface file for the Vision System. The development of this GUI utility was 
done using **Qt 5 Designer**. One could write program to completely design the GUI interface instead 
of using this nice utility, but the utility was very nice and useful.

To install **Qt 5 Designer**:
```
$ sudo apt-get install qttools5-dev-tools
$ sudo apt-get install qttools5-dev
```


## Contributors

- [Gary](https://github.com/itsecgary)
- [Eric](https://github.com/ephan1068)


## Resources & References
[TCP vs UDP](https://www.lifesize.com/en/blog/tcp-vs-udp/)


