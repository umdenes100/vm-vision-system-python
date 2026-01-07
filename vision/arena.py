from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import time

from vision.aruco import ArucoDetector, ArucoMarker


@dataclass
class ArenaConfig:
    # IDs that must be present to define the arena (used to refresh crop transform)
    required_corner_ids: Tuple[int, int, int, int] = (0, 1, 2, 3)

    # Output crop size (pixels)
    output_width: int = 1000
    output_height: int = 700

    # Draw marker IDs on overlay/crop
    draw_ids: bool = True

    # Line thickness for marker boxes
    box_thickness: int = 2

    # Only recompute the crop transform this often (seconds)
    crop_refresh_seconds: int = 600  # 10 minutes


class ArenaProcessor:
    """
    Produces:
      - latest_overlay_jpeg: raw frame with green boxes around all detected ArUco markers
      - latest_cropped_jpeg: warped arena crop

    Crop stability:
      - Maintains a cached homography (warp matrix) and keeps producing cropped frames
        even if markers 0–3 temporarily disappear.
      - Recomputes crop transform at most once every `crop_refresh_seconds`.
    """

    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg
        self.detector = ArucoDetector(dict_name="DICT_4X4_50")

        self.latest_overlay_jpeg: Optional[bytes] = None
        self.latest_cropped_jpeg: Optional[bytes] = None

        self._frames_processed = 0

        # Cached warp transform and timing
        self._M_cached: Optional[np.ndarray] = None
        self._M_last_update_monotonic: float = 0.0

    def stats(self) -> dict:
        return {
            "frames_processed": self._frames_processed,
            "have_cached_homography": self._M_cached is not None,
            "seconds_since_crop_refresh": (
                None if self._M_cached is None else (time.monotonic() - self._M_last_update_monotonic)
            ),
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
        corners: (N,2) float32
        returns TL, TR, BR, BL based on:
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

    def _maybe_refresh_homography(self, markers: Dict[int, ArucoMarker]) -> None:
        """
        Refresh cached homography only if:
          - no cache yet, OR
          - refresh interval elapsed AND required markers are present
        """
        now = time.monotonic()

        need_first = self._M_cached is None
        interval_elapsed = (now - self._M_last_update_monotonic) >= float(self.cfg.crop_refresh_seconds)

        if not need_first and not interval_elapsed:
            return

        if not self._have_required_corners(markers):
            # Can't refresh now; keep old transform if we have one.
            return

        # Use all corners from required markers to robustly define outer arena quad.
        pts = []
        for mid in self.cfg.required_corner_ids:
            pts.append(markers[mid].corners)
        all_corners = np.vstack(pts).astype(np.float32)  # (16,2)

        src = self._outermost_quad_from_corners(all_corners)

        dst = np.array(
            [
                [0, 0],
                [self.cfg.output_width - 1, 0],
                [self.cfg.output_width - 1, self.cfg.output_height - 1],
                [0, self.cfg.output_height - 1],
            ],
            dtype=np.float32,
        )

        self._M_cached = cv2.getPerspectiveTransform(src, dst)
        self._M_last_update_monotonic = now

    @staticmethod
    def _warp_points(M: np.ndarray, pts_xy: np.ndarray) -> np.ndarray:
        """
        pts_xy: (N,2) float32
        returns: (N,2) float32 warped points
        """
        pts = pts_xy.reshape(-1, 1, 2).astype(np.float32)
        warped = cv2.perspectiveTransform(pts, M)
        return warped.reshape(-1, 2)

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        markers = self.detector.detect(frame_bgr)

        # Overlay: raw + green boxes
        overlay = frame_bgr.copy()
        self._draw_marker_boxes(overlay, markers, self.cfg.box_thickness, self.cfg.draw_ids)
        overlay_jpg = self._encode_jpeg(overlay, quality=80)
        if overlay_jpg is not None:
            self.latest_overlay_jpeg = overlay_jpg

        # Crop: update cached transform at most every 10 minutes (or first time)
        self._maybe_refresh_homography(markers)

        if self._M_cached is None:
            # No crop available yet.
            self.latest_cropped_jpeg = None
            self._frames_processed += 1
            return

        M = self._M_cached

        warped = cv2.warpPerspective(frame_bgr, M, (self.cfg.output_width, self.cfg.output_height))

        # Draw green boxes for all detected markers on the CROPPED view as well.
        # Transform each marker's corners and draw in warped coordinate space.
        for mid, m in markers.items():
            warped_corners = self._warp_points(M, m.corners)
            pts = warped_corners.astype(int).reshape(-1, 1, 2)
            cv2.polylines(warped, [pts], isClosed=True, color=(0, 255, 0), thickness=self.cfg.box_thickness)

            if self.cfg.draw_ids:
                wc = self._warp_points(M, np.array([[m.center[0], m.center[1]]], dtype=np.float32))[0]
                cx, cy = int(wc[0]), int(wc[1])
                cv2.putText(
                    warped,
                    str(mid),
                    (cx + 6, cy - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

        cropped_jpg = self._encode_jpeg(warped, quality=80)
        if cropped_jpg is not None:
            self.latest_cropped_jpeg = cropped_jpg

        self._frames_processed += 1
