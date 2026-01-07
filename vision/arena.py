from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import time

from vision.aruco import ArucoDetector, ArucoMarker


@dataclass
class ArenaConfig:
    # Corner marker layout:
    # 0 = BL, 1 = TL, 2 = TR, 3 = BR
    id_bl: int = 0
    id_tl: int = 1
    id_tr: int = 2
    id_br: int = 3

    # Output crop size (pixels) — TRUE 2:1
    output_width: int = 1800
    output_height: int = 900

    # Draw marker IDs
    draw_ids: bool = True
    box_thickness: int = 2

    # Crop refresh behavior
    crop_refresh_seconds: int = 600

    # Border based on marker size
    border_marker_fraction: float = 0.5

    # EXTRA vertical padding (fraction of arena height)
    # Prevents top/bottom ArUco clipping after warp
    vertical_padding_fraction: float = 0.06  # 6% top + bottom


class ArenaProcessor:
    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg
        self.detector = ArucoDetector(dict_name="DICT_4X4_50")

        self.latest_overlay_jpeg: Optional[bytes] = None
        self.latest_cropped_jpeg: Optional[bytes] = None

        self._M_cached: Optional[np.ndarray] = None
        self._M_last_update_monotonic: float = 0.0

    @staticmethod
    def _encode_jpeg(bgr: np.ndarray, quality: int = 80) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return buf.tobytes() if ok else None

    def _draw_marker_boxes(self, img, markers):
        for mid, m in markers.items():
            pts = m.corners.astype(int).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], True, (0, 255, 0), self.cfg.box_thickness)
            if self.cfg.draw_ids:
                cx, cy = map(int, m.center)
                cv2.putText(img, str(mid), (cx + 6, cy - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    @staticmethod
    def _mean_marker_size(marker: ArucoMarker) -> float:
        c = marker.corners
        return float(np.mean([
            np.linalg.norm(c[0] - c[1]),
            np.linalg.norm(c[1] - c[2]),
            np.linalg.norm(c[2] - c[3]),
            np.linalg.norm(c[3] - c[0]),
        ]))

    @staticmethod
    def _warp_points(M, pts):
        return cv2.perspectiveTransform(
            pts.reshape(-1, 1, 2).astype(np.float32), M
        ).reshape(-1, 2)

    def _compute_src_quad(self, markers):
        bl = markers[self.cfg.id_bl]
        tl = markers[self.cfg.id_tl]
        tr = markers[self.cfg.id_tr]
        br = markers[self.cfg.id_br]

        arena_center = np.mean(
            np.array([bl.center, tl.center, tr.center, br.center], dtype=np.float32),
            axis=0
        )

        def outer_corner(m):
            d = np.linalg.norm(m.corners - arena_center, axis=1)
            return m.corners[np.argmax(d)]

        src = np.array([
            outer_corner(tl),
            outer_corner(tr),
            outer_corner(br),
            outer_corner(bl),
        ], dtype=np.float32)

        avg_marker_px = np.mean([
            self._mean_marker_size(bl),
            self._mean_marker_size(tl),
            self._mean_marker_size(tr),
            self._mean_marker_size(br),
        ])

        return src, avg_marker_px

    def _expand_quad(self, quad, border_px):
        center = np.mean(quad, axis=0)
        out = []
        for p in quad:
            v = p - center
            out.append(p + border_px * v / np.linalg.norm(v))
        return np.array(out, dtype=np.float32)

    def _apply_vertical_padding(self, quad):
        """
        Expands quad vertically to prevent top/bottom clipping.
        """
        pad = self.cfg.vertical_padding_fraction
        if pad <= 0:
            return quad

        top = (quad[0] + quad[1]) / 2
        bottom = (quad[2] + quad[3]) / 2
        v = bottom - top

        quad[0] -= v * pad
        quad[1] -= v * pad
        quad[2] += v * pad
        quad[3] += v * pad
        return quad

    def _maybe_refresh_homography(self, markers):
        now = time.monotonic()
        if self._M_cached and (now - self._M_last_update_monotonic) < self.cfg.crop_refresh_seconds:
            return

        if not all(mid in markers for mid in (0, 1, 2, 3)):
            return

        src, marker_px = self._compute_src_quad(markers)
        src = self._expand_quad(src, marker_px * self.cfg.border_marker_fraction)
        src = self._apply_vertical_padding(src)

        dst = np.array([
            [0, 0],
            [self.cfg.output_width - 1, 0],
            [self.cfg.output_width - 1, self.cfg.output_height - 1],
            [0, self.cfg.output_height - 1],
        ], dtype=np.float32)

        self._M_cached = cv2.getPerspectiveTransform(src, dst)
        self._M_last_update_monotonic = now

    def process_bgr(self, frame):
        markers = self.detector.detect(frame)

        overlay = frame.copy()
        self._draw_marker_boxes(overlay, markers)
        self.latest_overlay_jpeg = self._encode_jpeg(overlay)

        self._maybe_refresh_homography(markers)
        if self._M_cached is None:
            self.latest_cropped_jpeg = None
            return

        warped = cv2.warpPerspective(
            frame, self._M_cached,
            (self.cfg.output_width, self.cfg.output_height)
        )

        for m in markers.values():
            pts = self._warp_points(self._M_cached, m.corners).astype(int)
            cv2.polylines(warped, [pts.reshape(-1, 1, 2)], True, (0, 255, 0), self.cfg.box_thickness)

        self.latest_cropped_jpeg = self._encode_jpeg(warped)
