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


# ---------- Debug helpers (throttled) ----------
_LAST_DBG = 0.0
_LAST_MARKER_DBG = 0.0
_LAST_WARP_DBG = 0.0


def _dbg(msg: str, every_s: float = 2.0) -> None:
    global _LAST_DBG
    now = time.perf_counter()
    if now - _LAST_DBG >= every_s:
        _LAST_DBG = now
        print(msg)


def _dbg_markers(ids, every_s: float = 2.0) -> None:
    global _LAST_MARKER_DBG
    now = time.perf_counter()
    if now - _LAST_MARKER_DBG >= every_s:
        _LAST_MARKER_DBG = now
        if ids is None:
            print("[VS][DBG] No markers detected")
        else:
            present = sorted(int(i) for i in ids)
            missing = [i for i in (0, 1, 2, 3) if i not in present]
            print(f"[VS][DBG] markers present={present} missing_corners={missing}")


def _dbg_warp(msg: str, every_s: float = 2.0) -> None:
    global _LAST_WARP_DBG
    now = time.perf_counter()
    if now - _LAST_WARP_DBG >= every_s:
        _LAST_WARP_DBG = now
        print(msg)


# ---------- Core logic ----------
def _try_compute_homography(raw_frame) -> None:
    """
    Compute dr_op.H and dr_op.camera_matrix once the four corner markers (0..3) are visible.
    Also compute dr_op.inverse_matrix because vs_arena overlay routines depend on it.
    """
    if dr_op.H is not None and dr_op.camera_matrix is not None:
        return

    corners, ids, _ = detector.detectMarkers(raw_frame)
    if ids is None or corners is None:
        _dbg_markers(None)
        return

    ids = [int(i[0]) for i in ids]
    corners = [c[0] for c in corners]

    _dbg_markers(ids)

    # Require markers 0..3
    if not all(i in ids for i in (0, 1, 2, 3)):
        return

    marker_list = [(i, corners[ids.index(i)]) for i in (0, 1, 2, 3)]

    camera_height, camera_width = raw_frame.shape[:2]  # (h, w)
    try:
        H, camera_matrix = getHomographyMatrix(marker_list, camera_width, camera_height)
        dr_op.H = H
        dr_op.camera_matrix = camera_matrix

        # inverse_matrix is used by createObstacles/createMission
        try:
            dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
        except Exception as e:
            dr_op.inverse_matrix = None
            print(f"[VS][DBG] inverse_matrix compute failed: {e}")

        print("[VS] Homography/camera_matrix computed ✅ (crop/warp now possible)")
    except Exception as e:
        print(f"[VS][DBG] getHomographyMatrix failed: {e}")


def process_frame(raw_frame):
    """
    Draw detected markers, update dr_op marker states, and draw overlays.
    Returns a frame that is still in camera pixel space (raw view). The crop/zoom is applied later.
    """
    display = raw_frame

    try:
        corners, ids, _ = detector.detectMarkers(raw_frame)
        display = cv2.aruco.drawDetectedMarkers(raw_frame.copy(), corners)

        if ids is not None and corners is not None:
            ids = [int(i[0]) for i in ids]
            corners = [c[0] for c in corners]

            # If homography isn't ready yet, attempt here too (helps if _try_compute_homography misses)
            if dr_op.H is None or dr_op.camera_matrix is None:
                if all(i in ids for i in (0, 1, 2, 3)):
                    marker_list = [(i, corners[ids.index(i)]) for i in (0, 1, 2, 3)]
                    h, w = raw_frame.shape[:2]
                    dr_op.H, dr_op.camera_matrix = getHomographyMatrix(marker_list, w, h)
                    try:
                        dr_op.inverse_matrix = np.linalg.pinv(dr_op.H)
                    except Exception:
                        dr_op.inverse_matrix = None
                    print("[VS] Homography/camera_matrix computed ✅ (from process_frame)")

            # processMarkers() returns a DICT in your repo: {id: ProcessedMarker}
            try:
                markers_dict = processMarkers(zip(ids, corners))
                if isinstance(markers_dict, dict):
                    for mid, marker in markers_dict.items():
                        dr_op.aruco_markers[mid] = marker
            except Exception as e:
                _dbg(f"[VS][DBG] processMarkers failed: {e}", every_s=1.5)

        # Overlays require inverse_matrix + state params
        inv = getattr(dr_op, "inverse_matrix", None)
        if inv is not None:
            try:
                display = createObstacles(display, inv, dr_op.randomization)
            except Exception as e:
                _dbg(f"[VS][DBG] createObstacles failed: {e}", every_s=1.5)

            try:
                display = createMission(display, inv, dr_op.otv_start_dir, dr_op.mission_loc, dr_op.otv_start_loc)
            except Exception as e:
                _dbg(f"[VS][DBG] createMission failed: {e}", every_s=1.5)
        else:
            _dbg("[VS][DBG] inverse_matrix not ready; overlays skipped", every_s=2.0)

        return display

    except Exception as e:
        _dbg(f"[VS][DBG] process_frame exception: {e}", every_s=1.0)
        return raw_frame


def start_image_processing(port: int = 5000):
    """
    Main image loop:
      - read raw stream frames
      - compute homography/camera_matrix when possible
      - draw markers/overlays
      - warpPerspective using dr_op.camera_matrix (this is the crop/zoom you expect)
      - send JPEG to browser
    """
    global last_sleep

    cam = StreamCamera(port=port)
    cam.start()

    while True:
        try:
            raw = cam.get_frame()
            if raw is None:
                _dbg("[VS][DBG] No frame received; restarting stream", every_s=1.0)
                cam.restart_stream()
                continue

            # Ensure homography/camera_matrix is computed ASAP
            if dr_op.H is None or dr_op.camera_matrix is None:
                _try_compute_homography(raw)

            display = process_frame(raw)

            # Apply crop/zoom warp (this was the old “cropping” behavior)
            if dr_op.camera_matrix is not None:
                h, w = display.shape[:2]
                try:
                    # dsize is (width, height)
                    display = cv2.warpPerspective(display, dr_op.camera_matrix, (w, h))
                    _dbg_warp("[VS][DBG] warpPerspective applied ✅", every_s=2.0)
                except Exception as e:
                    _dbg_warp(f"[VS][DBG] warpPerspective failed: {e}", every_s=2.0)
            else:
                _dbg_warp("[VS][DBG] camera_matrix is None -> NOT cropping yet", every_s=2.0)

            jpg = cv2.imencode(".jpg", display, [int(cv2.IMWRITE_JPEG_QUALITY), 30])[1].tobytes()
            send_frame(jpg)

        except Exception as e:
            _dbg(f"[VS][DBG] image loop exception: {e}", every_s=1.0)

        # FPS throttle
        sleep_time = (1 / target_fps) - (time.perf_counter() - last_sleep)
        if sleep_time > 0:
            time.sleep(sleep_time)
        last_sleep = time.perf_counter()
