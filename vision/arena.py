from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from vision.aruco import ArucoDetector, ArucoMarker


@dataclass
class ArenaConfig:
    # IDs that must be present to define the arena
    required_corner_ids: Tuple[int, int, int, int] = (0, 1, 2, 3)

    # Output crop size (pixels)
    output_width: int = 1000
    output_height: int = 700

    # Draw marker IDs on overlay
    draw_ids: bool = True

    # Line thickness for marker boxes
    box_thickness: int = 2


class ArenaProcessor:
    """
    Produces:
      - latest_overlay_jpeg: raw frame with green boxes around all detected ArUco markers
      - latest_cropped_jpeg: perspective-warped arena crop when markers 0-3 are all detected

    Crop logic:
      - Requires IDs 0-3 to be present.
      - Determines the arena quad (TL, TR, BR, BL) robustly by taking ALL corners
        of the four corner markers and selecting outermost points.
    """

    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg
        self.detector = ArucoDetector(dict_name="DICT_4X4_50")

        self.latest_overlay_jpeg: Optional[bytes] = None
        self.latest_cropped_jpeg: Optional[bytes] = None

        self._frames_processed = 0
        self._last_have_corners = False

    def stats(self) -> dict:
        return {
            "frames_processed": self._frames_processed,
            "have_arena_corners": self._last_have_corners,
        }

    @staticmethod
    def _draw_marker_boxes(
        img: np.ndarray,
        markers: Dict[int, ArucoMarker],
        thickness: int,
        draw_ids: bool,
    ) -> None:
        for mid, m in markers.items():
            pts = m.corners.astype(int).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], isClosed=True, color=(0, 255, 0), thickness=thickness)

            if draw_ids:
                cx, cy = int(m.center[0]), int(m.center[1])
                cv2.putText(
                    img,
                    str(mid),
                    (cx + 6, cy - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

    @staticmethod
    def _encode_jpeg(bgr: np.ndarray, quality: int = 80) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            return None
        return buf.tobytes()

    def _have_required_corners(self, markers: Dict[int, ArucoMarker]) -> bool:
        return all(mid in markers for mid in self.cfg.required_corner_ids)

    @staticmethod
    def _outermost_quad_from_corners(corners: np.ndarray) -> np.ndarray:
        """
        corners: (N,2) float32 of points.
        Returns points TL, TR, BR, BL using common heuristics:
          TL = min(x+y)
          BR = max(x+y)
          TR = max(x-y)
          BL = min(x-y)
        """
        s = corners[:, 0] + corners[:, 1]
        d = corners[:, 0] - corners[:, 1]

        tl = corners[np.argmin(s)]
        br = corners[np.argmax(s)]
        tr = corners[np.argmax(d)]
        bl = corners[np.argmin(d)]

        return np.array([tl, tr, br, bl], dtype=np.float32)

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        markers = self.detector.detect(frame_bgr)

        # Overlay: raw + green boxes
        overlay = frame_bgr.copy()
        self._draw_marker_boxes(overlay, markers, self.cfg.box_thickness, self.cfg.draw_ids)
        overlay_jpg = self._encode_jpeg(overlay, quality=80)
        if overlay_jpg is not None:
            self.latest_overlay_jpeg = overlay_jpg

        # Crop: require markers 0-3
        if not self._have_required_corners(markers):
            self._last_have_corners = False
            self.latest_cropped_jpeg = None
            self._frames_processed += 1
            return

        # Gather all 16 corners from markers 0-3 and compute outermost quad
        pts = []
        for mid in self.cfg.required_corner_ids:
            pts.append(markers[mid].corners)
        all_corners = np.vstack(pts).astype(np.float32)  # (16,2)

        src = self._outermost_quad_from_corners(all_corners)
        self._last_have_corners = True

        dst = np.array(
            [
                [0, 0],
                [self.cfg.output_width - 1, 0],
                [self.cfg.output_width - 1, self.cfg.output_height - 1],
                [0, self.cfg.output_height - 1],
            ],
            dtype=np.float32,
        )

        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(frame_bgr, M, (self.cfg.output_width, self.cfg.output_height))

        cropped_jpg = self._encode_jpeg(warped, quality=80)
        if cropped_jpg is not None:
            self.latest_cropped_jpeg = cropped_jpg

        self._frames_processed += 1
