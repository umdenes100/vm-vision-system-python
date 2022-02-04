# importing the necessary libraries
import cv2
import numpy as np
import vs_comm 
import vs_gui
import threading
from _thread import *
import time

drawing_options = {'draw_dest': False, 'draw_obstacles': False, 'draw_coord': False, 
                   'otv_start_loc': 0, 'otv_start_dir_theta': 0, 'mission_loc': 1,
                   'randomization': {}}
aruco_markers = {}

def draw_on_frame(frame):
    # TODO - detect aruco markers
    # TODO - draw aruco markers
    # TODO - draw arena
    #print("in progress...")
    return frame

def frame_capture(cap, connections):
    # Loop until the end of the video
    if (cap.isOpened()):
        ret, frame = cap.read()
        #cv2.waitKey(1) 
        # Display the resulting frame
        #cv2.imshow('Frame', frame)

        # TODO - draw on image
        new_frame = draw_on_frame(frame)

        try:
            jpeg_bytes = cv2.imencode('.jpg', new_frame)[1]
        
            # send frame to each of the connections in the connection list in vs_comm.py
            #vs_comm.send_frame(new_frame)
            vs_comm.send_frame(np.array(jpeg_bytes).tostring(), connections)
        except:
            # most likely camera changed
            pass
 
def start_image_processing(connections):
    while 1:
        # switch camera if user selected diff camera on GUI
        cap = connections.get_cam()
        frame_capture(cap, connections)

    cap.release()
    cv2.destroyAllWindows()

