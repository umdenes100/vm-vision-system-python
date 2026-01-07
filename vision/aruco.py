from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class ArucoMarker:
    marker_id: int
    corners: np.ndarray  # shape (4, 2), float32
    center: Tuple[float, float]


def _marker_center(corners: np.ndarray) -> Tuple[float, float]:
    # corners: (4,2)
    cx = float(np.mean(corners[:, 0]))
    cy = float(np.mean(corners[:, 1]))
    return (cx, cy)


class ArucoDetector:
    """
    Detect ArUco markers and return pixel-space locations.

    Output:
      - Dict[int, ArucoMarker] where corners are in image pixel coordinates.

    Notes:
      - Uses OpenCV's ArUco module (opencv-contrib-python).
      - Corners are returned in the standard OpenCV order:
        top-left, top-right, bottom-right, bottom-left (clockwise).
    """

    def __init__(
        self,
        dict_name: str = "DICT_4X4_50",
        adaptive_thresh: bool = True,
    ):
        self.dict_name = dict_name
        self.aruco_dict = self._load_dict(dict_name)
        self.params = cv2.aruco.DetectorParameters()

        # A few reasonable defaults (still conservative)
        if adaptive_thresh:
            # These can help in uneven lighting
            self.params.adaptiveThreshWinSizeMin = 3
            self.params.adaptiveThreshWinSizeMax = 23
            self.params.adaptiveThreshWinSizeStep = 10

        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.params)

    @staticmethod
    def _load_dict(dict_name: str):
        # Map string to cv2.aruco constant
        key = dict_name.strip().upper()
        if not key.startswith("DICT_"):
            key = "DICT_" + key

        if not hasattr(cv2.aruco, key):
            raise ValueError(f"Unknown ArUco dictionary: {dict_name}")

        return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, key))

    def detect(self, bgr: np.ndarray) -> Dict[int, ArucoMarker]:
        """
        Detect markers in a BGR image.

        Returns:
          dict: marker_id -> ArucoMarker
        """
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        corners_list, ids, _rejected = self.detector.detectMarkers(gray)

        markers: Dict[int, ArucoMarker] = {}

        if ids is None or len(ids) == 0:
            return markers

        # corners_list: list of arrays with shape (1,4,2)
        for corners, mid in zip(corners_list, ids.flatten().tolist()):
            c = corners.reshape(4, 2).astype(np.float32)
            markers[int(mid)] = ArucoMarker(
                marker_id=int(mid),
                corners=c,
                center=_marker_center(c),
            )

        return markers
