import logging
import time

import cv2
import numpy as np

from components.data import dr_op, StreamCamera
from components.visioncomponents.vs_arena import (
    getHomographyMatrix,
    processMarkers,
    createObstacles,
    createMission,
)
from components.communications.client_server import send_frame


# ---- ArUco setup ----
dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dictionary, params)

# ---- Streaming ----
target_fps = 15
last_sleep = time.perf_counter()
img_info = {'bytes_sent': 0, 'frames_sent': 0}


def process_frame(frame):
    """Detect markers, compute homography once, update dr_op marker state, and draw overlays."""
    try:
        corners, ids, _ = detector.detectMarkers(frame)
        frame = cv2.aruco.drawDetectedMarkers(frame, corners)

        if ids is None or corners is None:
            return frame

        ids = [i[0] for i in ids]
        corners = [c[0] for c in corners]

        # Build homography when we have the 4 corner markers (0..3)
        if dr_op.H is None:
            if len(ids) < 4 or any(i not in ids for i in range(4)):
                return frame

            marker_list = [(i, corners[ids.index(i)]) for i in range(4)]
            camera_height, camera_width = frame.shape[:2]
            dr_op.H, dr_op.camera_matrix = getHomographyMatrix(marker_list, camera_width, camera_height)
            logging.info("Homography computed.")

        # Process + record marker poses
        processed = processMarkers(zip(ids, corners))
        for marker in processed:
            dr_op.aruco_markers[marker.id] = marker

        # Draw obstacles/mission overlays
        frame = createObstacles(frame)
        frame = createMission(frame)

        return frame
    except Exception as e:
        logging.debug(f"process_frame error: {e}")
        return frame


def start_image_processing(port: int = 5000):
    """Main image loop: read stream frames and forward low-quality JPEGs to the client server."""
    global last_sleep

    cam = StreamCamera(port=port)
    cam.start()

    print_fps_time = time.perf_counter()

    while True:
        start = time.perf_counter()

        try:
            frame = cam.get_frame()
            if frame is not None:
                processed_frame = process_frame(frame)

                jpeg_bytes = cv2.imencode(
                    '.jpg',
                    processed_frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 30],
                )[1]

                img_info['bytes_sent'] += len(jpeg_bytes)
                img_info['frames_sent'] += 1

                send_frame(np.array(jpeg_bytes).tobytes())
            else:
                logging.debug('No frame received, restarting stream')
                cam.restart_stream()

        except Exception as e:
            logging.debug(f"Error in image processing loop: {e}")

        # FPS throttle
        sleep_time = (1 / target_fps) - (time.perf_counter() - last_sleep)
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_sleep = time.perf_counter()

        # Debug FPS log
        if time.perf_counter() - print_fps_time > 10:
            print_fps_time = time.perf_counter()
            try:
                logging.debug(f'{1 / (time.perf_counter() - start):.2f} fps')
            except ZeroDivisionError:
                pass

        img_info['bytes_sent'] = 0
        img_info['frames_sent'] = 0
