from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from vision.aruco import ArucoDetector, ArucoMarker


@dataclass
class ArenaConfig:
    # Marker IDs that define arena boundary
    corner_ids: Tuple[int, int, int, int] = (0, 1, 2, 3)  # TL, TR, BR, BL

    # Output crop size (pixels)
    output_width: int = 1000
    output_height: int = 700

    # If True, also draw marker IDs on overlay
    draw_ids: bool = True

    # Line thickness for marker boxes
    box_thickness: int = 2


class ArenaProcessor:
    """
    Uses ArUco detections to:
      1) Create an overlay image where all detected markers have green boxes
      2) If markers 0-3 are present, produce a perspective-warped arena crop

    Provides latest JPEG bytes for:
      - overlay (raw frame + green marker boxes)
      - cropped (warped crop based on markers 0-3) with boxes drawn too
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
    def _draw_marker_boxes(img: np.ndarray, markers: Dict[int, ArucoMarker], thickness: int, draw_ids: bool):
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

    def _get_arena_src_points(self, markers: Dict[int, ArucoMarker]) -> Optional[np.ndarray]:
        """
        Return 4 source points for perspective warp in TL, TR, BR, BL order.

        We assume IDs represent corners in this order:
          0 = top-left
          1 = top-right
          2 = bottom-right
          3 = bottom-left

        For each marker, we use a specific corner of the marker polygon:
          id0 -> corner 0 (top-left)
          id1 -> corner 1 (top-right)
          id2 -> corner 2 (bottom-right)
          id3 -> corner 3 (bottom-left)

        This works when markers are placed consistently with orientation.
        If your physical placement differs, we can adjust this mapping.
        """
        tl_id, tr_id, br_id, bl_id = self.cfg.corner_ids
        needed = [tl_id, tr_id, br_id, bl_id]
        if any(mid not in markers for mid in needed):
            return None

        tl = markers[tl_id].corners[0]
        tr = markers[tr_id].corners[1]
        br = markers[br_id].corners[2]
        bl = markers[bl_id].corners[3]

        return np.array([tl, tr, br, bl], dtype=np.float32)

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        """
        Run detection + overlay + (optional) crop on a single BGR frame.
        Updates latest_overlay_jpeg and latest_cropped_jpeg (if available).
        """
        markers = self.detector.detect(frame_bgr)

        # 1) Overlay: raw + green boxes around all detected markers
        overlay = frame_bgr.copy()
        self._draw_marker_boxes(overlay, markers, self.cfg.box_thickness, self.cfg.draw_ids)
        overlay_jpg = self._encode_jpeg(overlay, quality=80)
        if overlay_jpg is not None:
            self.latest_overlay_jpeg = overlay_jpg

        # 2) Arena crop (if 0-3 found)
        src = self._get_arena_src_points(markers)
        if src is None:
            self._last_have_corners = False
            self.latest_cropped_jpeg = None
        else:
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

            # Draw boxes on warped too (optional but requested)
            # Note: drawing marker boxes in warped space would require transforming corners.
            # For now we draw boxes on the overlay stream (raw image). The cropped view is the clean crop.
            cropped_jpg = self._encode_jpeg(warped, quality=80)
            if cropped_jpg is not None:
                self.latest_cropped_jpeg = cropped_jpg

        self._frames_processed += 1
