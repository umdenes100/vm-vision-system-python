import time

import cv2
import numpy as np

from components.data import dr_op, StreamCamera
from components.visioncomponents.vs_arena import (
    getHomographyMatrix,
    processMarkers,
)
from components.communications.client_server import send_frame


# ---- ArUco setup ----
dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dictionary, params)

# ---- Streaming ----
target_fps = 15
last_sleep = time.perf_counter()


def _try_compute_homography(raw_frame) -> None:
    """
    Compute homography and camera_matrix once markers 0..3 are visible.
    Also compute inverse_matrix (kept for compatibility with other modules).
    """
    if dr_op.H is not None and dr_op.camera_matrix is not None:
        return

    corners, ids, _ = detector.detectMarkers(raw_frame)
    if ids is None or corners is None:
        return

    ids = [int(i[0]) for i in ids]
    corners = [c[0] for c in corners]

    if not all(i in ids for i in (0, 1, 2, 3)):
        return

    marker_list = [(i, corners[ids.index(i)]) for i in (0, 1, 2, 3)]
    h, w = raw_frame.shape[:2]

    H, camera_matrix = getHomographyMatrix(marker_list, w, h)
    dr_op.H = H
    dr_op.camera_matrix = camera_matrix

    try:
        dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
    except Exception:
        dr_op.inverse_matrix = None


def process_frame(raw_frame):
    """
    Detect markers, update dr_op marker state.
    Returns a frame in camera pixel space. Warping/cropping is applied later.
    """
    corners, ids, _ = detector.detectMarkers(raw_frame)
    display = cv2.aruco.drawDetectedMarkers(raw_frame.copy(), corners)

    if ids is not None and corners is not None:
        ids = [int(i[0]) for i in ids]
        corners = [c[0] for c in corners]

        # Compute homography if needed (helps when _try_compute_homography misses)
        if dr_op.H is None or dr_op.camera_matrix is None:
            if all(i in ids for i in (0, 1, 2, 3)):
                marker_list = [(i, corners[ids.index(i)]) for i in (0, 1, 2, 3)]
                h, w = raw_frame.shape[:2]
                dr_op.H, dr_op.camera_matrix = getHomographyMatrix(marker_list, w, h)
                try:
                    dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
                except Exception:
                    dr_op.inverse_matrix = None

        # processMarkers returns a dict: {id: ProcessedMarker}
        markers = processMarkers(zip(ids, corners))
        if isinstance(markers, dict):
            for mid, marker in markers.items():
                dr_op.aruco_markers[mid] = marker

    # NOTE: No createObstacles(), no createMission() -> no white square/arrow, no pink circle.
    return display


def start_image_processing(port: int = 5000):
    """
    Main image loop:
      - read stream frames
      - compute homography
      - draw detected markers
      - warpPerspective (arena crop)
      - send JPEG to browser
    """
    global last_sleep

    cam = StreamCamera(port=port)
    cam.start()

    while True:
        raw = cam.get_frame()
        if raw is None:
            cam.restart_stream()
            continue

        if dr_op.H is None or dr_op.camera_matrix is None:
            _try_compute_homography(raw)

        display = process_frame(raw)

        # Apply arena crop / rectification
        if dr_op.camera_matrix is not None:
            h, w = display.shape[:2]
            display = cv2.warpPerspective(display, dr_op.camera_matrix, (w, h))

        jpg = cv2.imencode(
            ".jpg",
            display,
            [int(cv2.IMWRITE_JPEG_QUALITY), 30]
        )[1].tobytes()

        send_frame(jpg)

        # FPS throttle
        sleep_time = (1 / target_fps) - (time.perf_counter() - last_sleep)
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_sleep = time.perf_counter()
