# importing the necessary libraries
import cv2
import numpy as np
import aruco_marker
import arena
import vs_comm 
import vs_gui
import threading
from _thread import *
import time

#drawing_options = {'draw_dest': False, 'draw_obstacles': False, 'draw_coord': False, 
#                   'otv_start_loc': 0, 'otv_start_dir_theta': 0, 'mission_loc': 1,
#                   'randomization': {}}
#aruco_markers = {}

def draw_on_frame(frame, dr_op):
    arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_1000)
    arucoParams = cv2.aruco.DetectorParameters_create()
    (corners, ids, rejected) = cv2.aruco.detectMarkers(frame, arucoDict, parameters=arucoParams)
    frame = cv2.aruco.drawDetectedMarkers(frame,corners,ids)
    #print(f"drawing0 --- {ids}")
    #return frame

    if isinstance(ids, list): # sometimes the "ids" array can be NoneType
        #print(f"drawing1 --- {ids}")
        marker_list = []
        for x in range(len(ids)):
            p1 = aruco_marker.Marker(ids[x],corners[x][0][0],corners[x][0][1],corners[x][0][2],corners[x][0][3])
            marker_list.append(p1)
        
        H = arena.getHomographyMatrix(frame,marker_list)
        frame_after = arena.processMarkers(frame,marker_list,H) 
        print("successful frame_after")
    else:
        frame_after = frame

    # TODO - draw arena
    return frame_after

def frame_capture(cap, connections, dr_op):
    # Loop until the end of the video
    if (cap.isOpened()):
        ret, frame = cap.read()
        #cv2.waitKey(1) 
        #cv2.imshow('Frame', frame)

        try:
            new_frame = draw_on_frame(frame, dr_op)
            jpeg_bytes = cv2.imencode('.jpg', new_frame)[1]
        
            # send frame to each of the connections in the connection list in vs_comm.py
            vs_comm.send_frame(np.array(jpeg_bytes).tostring(), connections)
        except Exception as e:
            # most likely camera changed
            print(e)
            pass
 
def start_image_processing(connections, dr_op):
    while 1:
        # switch camera if user selected diff camera on GUI
        #cap = connections.get_cam()
        cap = connections.video
        frame_capture(cap, connections, dr_op)

    cap.release()
    cv2.destroyAllWindows()

