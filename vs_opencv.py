# importing the necessary libraries
import cv2
import numpy as np
import vs_arena
import vs_comm 
import vs_gui
from vs_main import Marker
import threading
from _thread import *
import time

def draw_on_frame(frame, dr_op):
    try:
        arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_1000)
        arucoParams = cv2.aruco.DetectorParameters_create()
        (corners, ids, rejected) = cv2.aruco.detectMarkers(frame, arucoDict, parameters=arucoParams)
        frame = cv2.aruco.drawDetectedMarkers(frame,corners,ids)

        if isinstance(ids, list) or isinstance(ids, np.ndarray): # sometimes the "ids" array can be NoneType
            #print(f"drawing1 --- {ids}")
            marker_list = []
            for x in range(len(ids)):
                p1 = Marker(ids[x],corners[x][0][0],corners[x][0][1],corners[x][0][2],corners[x][0][3])
                marker_list.append(p1)
        
            if dr_op.first:
                (dr_op.H, dr_op.first) = vs_arena.getHomographyMatrix(frame,marker_list)
                dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
            frame_after, dr_op.aruco_markers = vs_arena.processMarkers(frame, marker_list, dr_op.H, dr_op.inverse_matrix, dr_op) 
            #print(f"successful frame_after --- {dr_op.aruco_markers}")
        else:
            frame_after = frame
    except Exception as e:
        print(f'EXCEPTION (in draw_on_frame): {e}')
        return frame

    return frame_after

def frame_capture(cap, connections, dr_op):
    # Loop until the end of the video
    start = time.time()
    if (cap.isOpened()):
        try:
            ret, frame = cap.read()
            if ret:
                new_frame = draw_on_frame(frame, dr_op)
                jpeg_bytes = cv2.imencode('.jpg', new_frame)[1]
                vs_comm.send_frame(np.array(jpeg_bytes).tostring(), connections)
        except Exception as e:
            # most likely camera changed
            print(e)
            pass
        
 
def start_image_processing(connections, dr_op):
    cap = connections.video
    while 1:
        cap = connections.video
        if (cap.isOpened()):
            start = time.time()
            try:
                frame_capture(cap, connections, dr_op)
            except Exception as e:
                print(e)
                pass
            #print(f'time for frame capture = {(time.time() - start)} seconds')

    cap.release()
    cv2.destroyAllWindows()

