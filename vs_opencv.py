# importing the necessary libraries
import logging

import cv2
import numpy as np

import data
import vs_arena
from old import vs_comm
from vs_main import Marker
import time


def draw_on_frame(frame, dr_op):
    try:
        arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_1000)
        arucoParams = cv2.aruco.DetectorParameters_create()
        (corners, ids, rejected) = cv2.aruco.detectMarkers(frame, arucoDict, parameters=arucoParams)
        frame = cv2.aruco.drawDetectedMarkers(frame, corners, ids)

        if isinstance(ids, list) or isinstance(ids, np.ndarray):  # sometimes the "ids" array can be NoneType
            # print(f"drawing1 --- {ids}")
            marker_list = []
            for x in range(len(ids)):
                p1 = Marker(ids[x], corners[x][0][0], corners[x][0][1], corners[x][0][2], corners[x][0][3])
                marker_list.append(p1)

            if dr_op.first:
                (dr_op.H, dr_op.first) = vs_arena.getHomographyMatrix(frame, marker_list)
                dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
            frame_after, dr_op.aruco_markers = vs_arena.processMarkers(frame, marker_list, dr_op.H,
                                                                       dr_op.inverse_matrix, dr_op)
            # print(f"successful frame_after --- {drawing_options.aruco_markers}")
        else:
            frame_after = frame
    except Exception as e:
        exception_str = "EXCEPTION (in draw_on_frame): " + str(e) + "\n"
        print(exception_str)
        with open('errors.txt', 'a') as f:
            f.write(exception_str)
        return frame

    return frame_after


def start_image_processing():
    while True:
        start = time.perf_counter()  # start timer to calculate FPS
        cap = data.camera.get_camera()  # get video stream from connections object
        try:
            if cap.isOpened():
                ret, frame = cap.read()  # read frame from video stream
                if ret:
                    new_frame = draw_on_frame(frame, dr_op)
                    jpeg_bytes = cv2.imencode('.jpg', new_frame)[1]
                    vs_comm.send_frame(np.array(jpeg_bytes).tostring(), connections)
        except Exception as e:
            logging.debug(str(e))
            with open('errors.txt', 'a') as f:
                f.write(str(e))
        print(f'{1/(time.perf_counter() - start)} fps')