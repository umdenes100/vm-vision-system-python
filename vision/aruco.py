from dataclasses import dataclass
from typing import Dict, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class ArucoMarker:
    marker_id: int
    # Corners in OpenCV's ArUco order (clockwise):
    # top-left, top-right, bottom-right, bottom-left
    corners: np.ndarray  # shape (4, 2), float32
    center: Tuple[float, float]


def _marker_center(corners: np.ndarray) -> Tuple[float, float]:
    """Return center (cx, cy) of a (4,2) corner array."""
    cx = float(np.mean(corners[:, 0]))
    cy = float(np.mean(corners[:, 1]))
    return cx, cy


class ArucoDetector:
    """Detect ArUco markers and return pixel-space corner locations.

    Output:
      - Dict[int, ArucoMarker] where corners are in image pixel coordinates.

    Notes:
      - Uses OpenCV's ArUco module (opencv-contrib-python).
      - Corners are returned in OpenCV's standard order:
        top-left, top-right, bottom-right, bottom-left (clockwise).

    Dictionary:
      - This project uses IDs beyond 250 (e.g., 257, 467, 522, 697),
        so the default is DICT_4X4_1000 (IDs 0..999).
    """

    def __init__(
        self,
        dict_name: str = "DICT_4X4_1000",
        adaptive_thresh: bool = True,
    ):
        self.dict_name = dict_name
        self.aruco_dict = self._load_dict(dict_name)

        self.params = cv2.aruco.DetectorParameters()
        if adaptive_thresh:
            # Reasonable defaults for varying lighting
            self.params.adaptiveThreshWinSizeMin = 3
            self.params.adaptiveThreshWinSizeMax = 23
            self.params.adaptiveThreshWinSizeStep = 10

        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.params)

    @staticmethod
    def _load_dict(dict_name: str):
        key = (dict_name or "").strip().upper()
        if not key.startswith("DICT_"):
            key = "DICT_" + key
        if not hasattr(cv2.aruco, key):
            raise ValueError(f"Unknown ArUco dictionary: {dict_name}")
        return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, key))

    def detect(self, bgr: np.ndarray) -> Dict[int, ArucoMarker]:
        """Detect markers in a BGR frame.

        Returns:
          dict: marker_id -> ArucoMarker
        """
        corners_list, ids, _rejected = self.detector.detectMarkers(bgr)

        markers: Dict[int, ArucoMarker] = {}
        if ids is None or len(ids) == 0:
            return markers

        # corners_list: list of arrays with shape (1,4,2)
        for corners, mid in zip(corners_list, ids.flatten().tolist()):
            c = corners.reshape(4, 2).astype(np.float32)
            mid_i = int(mid)
            markers[mid_i] = ArucoMarker(
                marker_id=mid_i,
                corners=c,
                center=_marker_center(c),
            )

        return markers
