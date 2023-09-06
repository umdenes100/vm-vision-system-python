import logging
import sys
import threading

import components.communications.client_server
from components.communications.client_server import send_frame
from components.communications.esp_server import send_locations

if 'local' not in sys.argv:
    import cv2
    import numpy as np

from components.data import dr_op, camera
from components.visioncomponents.vs_arena import getHomographyMatrix, processMarkers, createObstacles, createMission
import time

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dictionary, parameters)
def draw_on_frame(frame):
    try:
        (corners, ids, rejected) = detector.detectMarkers(frame)
        frame = cv2.aruco.drawDetectedMarkers(frame, corners)
        if not (isinstance(ids, list) or isinstance(ids, np.ndarray)):
            return frame

        corners = [c[0] for c in corners]
        ids = [i[0] for i in ids]

        if dr_op.H is None:
            dr_op.H = getHomographyMatrix(zip(ids, corners))
            if dr_op.H is None:
                components.communications.client_server.send_error_message(
                    'At least one of the corner ArUco markers are not visible.')
                time.sleep(1)
                for y in range(50, frame.shape[0], 50):
                    frame = cv2.putText(frame, 'One of the corners is not visible - cannot initialize', (50, y),
                                        cv2.FONT_HERSHEY_TRIPLEX, 2,
                                        (0, 0, 255))

                return frame
            components.communications.client_server.send_error_message('Initialized Homography Matrix (All corners visible)')
            dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
        dr_op.aruco_markers = processMarkers(zip(ids, corners))

        if dr_op.draw_obstacles:
            frame = createObstacles(frame, dr_op.inverse_matrix, dr_op.randomization)

        if dr_op.draw_dest:
            frame = createMission(frame, dr_op.inverse_matrix, dr_op.otv_start_dir, dr_op.mission_loc,
                                  dr_op.otv_start_loc)

        if dr_op.draw_text:
            for marker in dr_op.aruco_markers.values():
                if marker.id not in range(3):
                    try:
                        frame = cv2.putText(frame, 'ID:' + str(marker.id), marker.pixels, cv2.FONT_HERSHEY_SIMPLEX, 1,
                                            (0, 255, 0))
                    except Exception as e:
                        print('exception: ' + str(marker), str(marker.pixels))
                        import traceback
                        print(traceback.format_exc())

        if dr_op.draw_arrows:
            def tuple_int(x):
                return tuple(map(int, x))

            for i, c in zip(ids, corners):
                if i not in range(4):
                    frame = cv2.arrowedLine(frame, tuple_int(c[0]), tuple_int(c[1]), (0, 255, 0), 2,
                                            tipLength=.4)

    except KeyboardInterrupt:
        exit()
    except Exception as e:
        logging.debug(str(e))
        import traceback
        print(traceback.format_exc())
    return frame


target_fps = 20
last_sleep = time.perf_counter()

img_info = {
    'bytes_sent': 0,
    'frames_sent': 0,
}


def start_image_processing():
    print_fps_time = time.perf_counter()
    send_locations_bool = True  # send locations to esp32 every other frame
    while True:
        # If a web client is connected
        # if len(communications.client_server.ws_server.clients) == 0 and len(communications.esp_server.ws_server.clients) == 0:
        #     logging.debug('No clients connected, slowing image processing to 1fps')
        #     time.sleep(1)
        start = time.perf_counter()  # start timer to calculate FPS
        cap = camera.get_camera()  # get video stream from connections object
        try:
            if cap.isOpened():
                ret, frame = cap.read()  # read frame from video stream
                if ret:
                    new_frame = draw_on_frame(frame)
                    if send_locations_bool:
                        threading.Thread(target=send_locations, name='Send Locations').start()
                    send_locations_bool = not send_locations_bool

                    jpeg_bytes = cv2.imencode('.jpg', new_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])[1]
                    img_info['bytes_sent'] += len(jpeg_bytes)
                    img_info['frames_sent'] += 1
                    # logging.log(f'Image size: {len(jpeg_bytes)} bytes')
                    send_frame(np.array(jpeg_bytes).tostring())  # send frame to web client
        except Exception as e:
            logging.debug(str(e))
        global last_sleep
        sleep_time = (1 / target_fps) - (time.perf_counter() - last_sleep)
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_sleep = time.perf_counter()

        if time.perf_counter() - print_fps_time > 10:
            print_fps_time = time.perf_counter()
            try:
                logging.debug(
                    f'{1 / (time.perf_counter() - start):.2f} fps - avg {img_info["bytes_sent"] / img_info["frames_sent"] / 1000:.0f} kb per frame')  # print FPS
            except ZeroDivisionError:
                pass
        img_info['bytes_sent'] = 0
        img_info['frames_sent'] = 0
