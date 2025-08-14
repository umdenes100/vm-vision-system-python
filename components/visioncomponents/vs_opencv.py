import json
import logging
import os
import sys
import threading
import time
import cv2
import numpy as np

import components.communications.client_server

from components.data import dr_op, camera
from components.visioncomponents.vs_arena import getHomographyMatrix, processMarkers, createObstacles, createMission
from components.communications.client_server import send_frame
from components.communications.esp_server import send_locations


config = {}
if os.path.isfile(os.path.expanduser('~/config.json')):
    with open(os.path.expanduser('~/config.json')) as f:
        config = json.load(f)

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dictionary, parameters)
camera_bounds = None

target_fps = 40 # Was originally 15 fps. Stream seems to only get 15fps anyways - this might be the RPI tho! Test this!!
last_sleep = time.perf_counter()

img_info = {
    'bytes_sent': 0,
    'frames_sent': 0,
}

def corners_found(ids):
    return len(ids) >= 4 and all([i in ids for i in range(4)])


def render_issue(issue: str, frame):
    components.communications.client_server.send_console_message(issue)
    for y in range(50, frame.shape[0], 50):
        frame = cv2.putText(frame, issue, (50, y), cv2.FONT_HERSHEY_TRIPLEX, 2, (0, 0, 255))

    return frame


def process_frame(frame):
    try:
        corners, ids, _ = detector.detectMarkers(frame)
        frame = cv2.aruco.drawDetectedMarkers(frame, corners)

        if ids is None or corners is None:
            return frame

        ids = [i[0] for i in ids]
        corners = [c[0] for c in corners]

        if dr_op.H is None:
            if len(ids) < 4 or any(i not in ids for i in range(4)):
                return frame

            dr_op.H, dr_op.camera_matrix = getHomographyMatrix(zip(ids, corners), frame.shape[1], frame.shape[0])
            dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)

        frame = cv2.warpPerspective(frame, dr_op.camera_matrix, (frame.shape[1], frame.shape[0]))
        dr_op.aruco_markers = processMarkers(zip(ids, corners))

        return frame

    except Exception as e:
        logging.debug(f"Exception in process_frame: {e}")
        return frame


def start_image_processing():
    print_fps_time = time.perf_counter()
    send_locations_bool = True

    while True:
        start = time.perf_counter()

        try:
            frame = camera.get_frame()
            if frame is not None:
                processed_frame = process_frame(frame)

                #if send_locations_bool:
                    # Might not be neccessary?
                    #threading.Thread(target=send_locations, name='Send Locations').start()
                send_locations_bool = not send_locations_bool

                jpeg_bytes = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])[1]
                img_info['bytes_sent'] += len(jpeg_bytes)
                img_info['frames_sent'] += 1

                send_frame(np.array(jpeg_bytes).tobytes())

            else:
                logging.debug('No frame received, restarting stream')
                camera.restart_stream()

        except Exception as e:
            logging.debug(f"Error in image processing loop: {e}")

        global last_sleep
        sleep_time = (1 / target_fps) - (time.perf_counter() - last_sleep)
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_sleep = time.perf_counter()

        if time.perf_counter() - print_fps_time > 10:
            print_fps_time = time.perf_counter()
            try:
                logging.debug(f'{1 / (time.perf_counter() - start):.2f} fps')
            except ZeroDivisionError:
                pass

        img_info['bytes_sent'] = 0
        img_info['frames_sent'] = 0
