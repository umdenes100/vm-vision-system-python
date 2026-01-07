from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import time

from vision.aruco import ArucoDetector, ArucoMarker


@dataclass
class ArenaConfig:
    # 0 = BL, 1 = TL, 2 = TR, 3 = BR
    id_bl: int = 0
    id_tl: int = 1
    id_tr: int = 2
    id_br: int = 3

    # Output crop size (pixels) — 2:1
    output_width: int = 1800
    output_height: int = 900

    draw_ids: bool = True
    box_thickness: int = 2

    crop_refresh_seconds: int = 600  # 10 min
    border_marker_fraction: float = 0.5

    # Extra vertical padding as a fraction of arena vertical axis (smaller than before)
    vertical_padding_fraction: float = 0.025  # 2.5% top + 2.5% bottom

    # JPEG quality for the cropped output (lower = faster)
    crop_jpeg_quality: int = 70
    overlay_jpeg_quality: int = 80


class ArenaProcessor:
    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg
        self.detector = ArucoDetector(dict_name="DICT_4X4_50")

        self.latest_overlay_jpeg: Optional[bytes] = None
        self.latest_cropped_jpeg: Optional[bytes] = None

        self._frames_processed = 0
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
    def _encode_jpeg(bgr: np.ndarray, quality: int) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else None

    @staticmethod
    def _draw_marker_boxes(img: np.ndarray, markers: Dict[int, ArucoMarker], thickness: int, draw_ids: bool) -> None:
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

    def _have_corner_markers(self, markers: Dict[int, ArucoMarker]) -> bool:
        needed = [self.cfg.id_bl, self.cfg.id_tl, self.cfg.id_tr, self.cfg.id_br]
        return all(mid in markers for mid in needed)

    @staticmethod
    def _mean_marker_size_px(marker: ArucoMarker) -> float:
        c = marker.corners
        edges = [
            np.linalg.norm(c[0] - c[1]),
            np.linalg.norm(c[1] - c[2]),
            np.linalg.norm(c[2] - c[3]),
            np.linalg.norm(c[3] - c[0]),
        ]
        return float(np.mean(edges))

    @staticmethod
    def _warp_points(M: np.ndarray, pts_xy: np.ndarray) -> np.ndarray:
        pts = pts_xy.reshape(-1, 1, 2).astype(np.float32)
        warped = cv2.perspectiveTransform(pts, M)
        return warped.reshape(-1, 2)

    @staticmethod
    def _expand_quad_radial(src: np.ndarray, border_px: float) -> np.ndarray:
        if border_px <= 0:
            return src
        centroid = np.mean(src, axis=0)
        out = []
        for p in src:
            v = p - centroid
            n = float(np.linalg.norm(v))
            if n < 1e-6:
                out.append(p)
            else:
                out.append(p + (border_px * v / n))
        return np.array(out, dtype=np.float32)

    def _apply_vertical_padding(self, src: np.ndarray) -> np.ndarray:
        pad = float(self.cfg.vertical_padding_fraction)
        if pad <= 0:
            return src

        # src order: TL, TR, BR, BL
        top_mid = (src[0] + src[1]) * 0.5
        bot_mid = (src[2] + src[3]) * 0.5
        v = bot_mid - top_mid

        src2 = src.copy()
        src2[0] -= v * pad
        src2[1] -= v * pad
        src2[2] += v * pad
        src2[3] += v * pad
        return src2

    def _compute_src_quad_from_corner_ids(self, markers: Dict[int, ArucoMarker]) -> Tuple[np.ndarray, float]:
        bl = markers[self.cfg.id_bl]
        tl = markers[self.cfg.id_tl]
        tr = markers[self.cfg.id_tr]
        br = markers[self.cfg.id_br]

        arena_center = np.mean(
            np.array([bl.center, tl.center, tr.center, br.center], dtype=np.float32),
            axis=0,
        )

        def outer_corner(m: ArucoMarker) -> np.ndarray:
            d = np.linalg.norm(m.corners - arena_center.reshape(1, 2), axis=1)
            return m.corners[int(np.argmax(d))].astype(np.float32)

        p_tl = outer_corner(tl)
        p_tr = outer_corner(tr)
        p_br = outer_corner(br)
        p_bl = outer_corner(bl)

        sizes = [
            self._mean_marker_size_px(bl),
            self._mean_marker_size_px(tl),
            self._mean_marker_size_px(tr),
            self._mean_marker_size_px(br),
        ]
        avg_marker_px = float(np.mean(sizes))

        src = np.array([p_tl, p_tr, p_br, p_bl], dtype=np.float32)
        return src, avg_marker_px

    def _maybe_refresh_homography(self, markers: Dict[int, ArucoMarker]) -> None:
        now = time.monotonic()

        need_first = self._M_cached is None
        interval_elapsed = (now - self._M_last_update_monotonic) >= float(self.cfg.crop_refresh_seconds)

        if not need_first and not interval_elapsed:
            return

        if not self._have_corner_markers(markers):
            return

        src, avg_marker_px = self._compute_src_quad_from_corner_ids(markers)
        border_px = float(self.cfg.border_marker_fraction) * avg_marker_px
        src = self._expand_quad_radial(src, border_px)
        src = self._apply_vertical_padding(src)

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

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        markers = self.detector.detect(frame_bgr)

        # Overlay
        overlay = frame_bgr.copy()
        self._draw_marker_boxes(overlay, markers, self.cfg.box_thickness, self.cfg.draw_ids)
        overlay_jpg = self._encode_jpeg(overlay, self.cfg.overlay_jpeg_quality)
        if overlay_jpg is not None:
            self.latest_overlay_jpeg = overlay_jpg

        # Crop
        self._maybe_refresh_homography(markers)

        if self._M_cached is None:
            self.latest_cropped_jpeg = None
            self._frames_processed += 1
            return

        M = self._M_cached
        warped = cv2.warpPerspective(frame_bgr, M, (self.cfg.output_width, self.cfg.output_height))

        # Draw marker boxes onto cropped view
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

        cropped_jpg = self._encode_jpeg(warped, self.cfg.crop_jpeg_quality)
        if cropped_jpg is not None:
            self.latest_cropped_jpeg = cropped_jpg

        self._frames_processed += 1
