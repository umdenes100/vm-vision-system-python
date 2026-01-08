from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import time
import math

from utils.logging import web_info
from vision.aruco import ArucoDetector, ArucoMarker


@dataclass
class ArenaConfig:
    # Corner marker layout in the arena:
    # 0=Bottom Left, 1=Top Left, 2=Top Right, 3=Bottom Right
    id_bl: int = 0
    id_tl: int = 1
    id_tr: int = 2
    id_br: int = 3

    # Physical coordinates of the *origin* of each corner marker (units arbitrary, but consistent)
    # User-specified:
    #   0: (0,0), 1:(0,2), 2:(4,2), 3:(4,0)
    arena_bl: Tuple[float, float] = (0.0, 0.0)
    arena_tl: Tuple[float, float] = (0.0, 2.0)
    arena_tr: Tuple[float, float] = (4.0, 2.0)
    arena_br: Tuple[float, float] = (4.0, 0.0)

    # Output crop size (pixels)
    output_width: int = 1000
    output_height: int = 500

    # How often to refresh the crop/arena homography from markers 0-3 (seconds)
    crop_refresh_seconds: float = 600.0  # 10 minutes

    # Add a border outside the 0-3 quad, relative to a marker's average size (px)
    border_marker_fraction: float = 0.5

    # Additional vertical padding proportional to quad vertical span (helps prevent top/bottom clipping)
    vertical_padding_fraction: float = 0.01

    # JPEG encoding quality
    overlay_jpeg_quality: int = 80
    crop_jpeg_quality: int = 75

    # Drawing
    box_thickness: int = 2
    draw_ids: bool = True


class ArenaProcessor:
    """Detect markers, draw overlays, compute a stable crop, and map marker pose to arena coords.

    Responsibilities:
      - Uses ArucoDetector to discover & localize all markers (pixel space).
      - Uses corner markers 0-3 to compute:
          (a) a crop transform for a 2:1 MJPEG stream
          (b) a pixel->arena transform for (x, y) + heading
      - Produces:
          latest_overlay_jpeg: full frame with green boxes + arrows
          latest_cropped_jpeg: cropped/warped frame with same overlays
      - Emits system-printouts once per second with per-marker (x, y, theta).
    """

    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg

        # Use a dictionary that supports high marker IDs (0..999).
        self.detector = ArucoDetector(dict_name="DICT_4X4_1000")

        self.latest_overlay_jpeg: Optional[bytes] = None
        self.latest_cropped_jpeg: Optional[bytes] = None

        # Cached transforms refreshed occasionally
        self._M_img_to_crop: Optional[np.ndarray] = None
        self._H_img_to_arena: Optional[np.ndarray] = None
        self._last_xform_update_monotonic: float = 0.0

        # Rate-limit for system printouts
        self._last_print_monotonic: float = 0.0

    @staticmethod
    def _encode_jpeg(bgr: np.ndarray, quality: int) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else None

    @staticmethod
    def _marker_origin_px(m: ArucoMarker) -> np.ndarray:
        # Bottom-left corner is the marker origin (user requirement).
        # OpenCV corner order: TL, TR, BR, BL
        return m.corners[3].astype(np.float32)

    @staticmethod
    def _marker_topleft_px(m: ArucoMarker) -> np.ndarray:
        return m.corners[0].astype(np.float32)

    @staticmethod
    def _draw_marker_boxes_and_arrows(
        img: np.ndarray,
        markers: Dict[int, ArucoMarker],
        thickness: int,
        draw_ids: bool,
    ) -> None:
        for mid, m in markers.items():
            pts = m.corners.astype(int).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], isClosed=True, color=(0, 255, 0), thickness=thickness)

            # Arrow: from origin (bottom-left) to top-left (along left edge)
            o = m.corners[3].astype(int)
            tl = m.corners[0].astype(int)
            cv2.arrowedLine(img, tuple(o), tuple(tl), color=(0, 255, 0), thickness=thickness, tipLength=0.25)

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
        return (
            self.cfg.id_bl in markers
            and self.cfg.id_tl in markers
            and self.cfg.id_tr in markers
            and self.cfg.id_br in markers
        )

    @staticmethod
    def _mean_marker_size_px(marker: ArucoMarker) -> float:
        # Rough size: average edge length
        c = marker.corners
        edges = [
            np.linalg.norm(c[0] - c[1]),
            np.linalg.norm(c[1] - c[2]),
            np.linalg.norm(c[2] - c[3]),
            np.linalg.norm(c[3] - c[0]),
        ]
        return float(np.mean(edges))

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
        top_mid = (src[0] + src[1]) * 0.5
        bot_mid = (src[2] + src[3]) * 0.5
        v = bot_mid - top_mid
        src2 = src.copy()
        src2[0] -= v * pad
        src2[1] -= v * pad
        src2[2] += v * pad
        src2[3] += v * pad
        return src2

    def _compute_transforms_from_corners(self, markers: Dict[int, ArucoMarker]) -> None:
        # We use the *marker origin* (bottom-left) as the correspondence point.
        bl = markers[self.cfg.id_bl]
        tl = markers[self.cfg.id_tl]
        tr = markers[self.cfg.id_tr]
        br = markers[self.cfg.id_br]

        src_arena = np.array(
            [
                self._marker_origin_px(bl),
                self._marker_origin_px(tl),
                self._marker_origin_px(tr),
                self._marker_origin_px(br),
            ],
            dtype=np.float32,
        )

        # Crop transform uses outer corners of the marker quads to make a stable border.
        # For cropping, we want the *arena boundary*; we approximate by using the outer-most corner
        # of each marker quad relative to the arena.
        def outer_corner(m: ArucoMarker, which: str) -> np.ndarray:
            c = m.corners
            if which == "bl":
                return c[3]  # bottom-left
            if which == "tl":
                return c[0]  # top-left
            if which == "tr":
                return c[1]  # top-right
            if which == "br":
                return c[2]  # bottom-right
            raise ValueError(which)

        src_crop = np.array(
            [
                outer_corner(bl, "bl"),
                outer_corner(tl, "tl"),
                outer_corner(tr, "tr"),
                outer_corner(br, "br"),
            ],
            dtype=np.float32,
        )

        # Border size based on average marker size
        mean_size = float(
            np.mean(
                [
                    self._mean_marker_size_px(bl),
                    self._mean_marker_size_px(tl),
                    self._mean_marker_size_px(tr),
                    self._mean_marker_size_px(br),
                ]
            )
        )
        border_px = mean_size * float(self.cfg.border_marker_fraction)
        src_crop = self._expand_quad_radial(src_crop, border_px)
        src_crop = self._apply_vertical_padding(src_crop)

        dst_crop = np.array(
            [
                [0, 0],
                [self.cfg.output_width - 1, 0],
                [self.cfg.output_width - 1, self.cfg.output_height - 1],
                [0, self.cfg.output_height - 1],
            ],
            dtype=np.float32,
        )

        # Arena coordinate target (x right, y up, as implied by corner coords)
        dst_arena = np.array(
            [
                self.cfg.arena_bl,
                self.cfg.arena_tl,
                self.cfg.arena_tr,
                self.cfg.arena_br,
            ],
            dtype=np.float32,
        )

        self._M_img_to_crop = cv2.getPerspectiveTransform(src_crop.astype(np.float32), dst_crop)
        self._H_img_to_arena = cv2.getPerspectiveTransform(src_arena.astype(np.float32), dst_arena)

    def _maybe_refresh_transforms(self, markers: Dict[int, ArucoMarker]) -> None:
        if not self._have_corner_markers(markers):
            return

        now = time.monotonic()
        if self._M_img_to_crop is not None and (now - self._last_xform_update_monotonic) < float(self.cfg.crop_refresh_seconds):
            return

        self._compute_transforms_from_corners(markers)
        self._last_xform_update_monotonic = now

    def _transform_point(self, H: np.ndarray, p: np.ndarray) -> Tuple[float, float]:
        pts = np.array([[p]], dtype=np.float32)  # (1,1,2)
        out = cv2.perspectiveTransform(pts, H)[0][0]
        return float(out[0]), float(out[1])

    def _marker_pose_arena(self, m: ArucoMarker) -> Optional[Tuple[float, float, float]]:
        if self._H_img_to_arena is None:
            return None

        o_px = self._marker_origin_px(m)
        tl_px = self._marker_topleft_px(m)

        ox, oy = self._transform_point(self._H_img_to_arena, o_px)
        tlx, tly = self._transform_point(self._H_img_to_arena, tl_px)

        vx = tlx - ox
        vy = tly - oy
        theta = math.atan2(vy, vx)  # radians
        return ox, oy, theta

    def _maybe_print_poses(self, markers: Dict[int, ArucoMarker]) -> None:
        now = time.monotonic()
        if (now - self._last_print_monotonic) < 1.0:
            return
        self._last_print_monotonic = now

        if not markers:
            web_info("Markers: none")
            return

        if self._H_img_to_arena is None:
            web_info(f"Markers detected: {sorted(markers.keys())} (waiting for corner markers 0-3 for arena coords)")
            return

        ids = sorted(markers.keys())
        web_info(f"Markers ({len(ids)}): " + ", ".join(str(i) for i in ids))
        for mid in ids:
            pose = self._marker_pose_arena(markers[mid])
            if pose is None:
                continue
            x, y, th = pose
            web_info(f"ID {mid:>4}: x={x:7.3f}, y={y:7.3f}, theta={math.degrees(th):7.2f} deg")

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        markers = self.detector.detect(frame_bgr)

        # Refresh transforms (stable crop/arena mapping)
        self._maybe_refresh_transforms(markers)

        # Overlay: full frame
        overlay = frame_bgr.copy()
        self._draw_marker_boxes_and_arrows(overlay, markers, self.cfg.box_thickness, self.cfg.draw_ids)
        overlay_jpg = self._encode_jpeg(overlay, self.cfg.overlay_jpeg_quality)
        if overlay_jpg is not None:
            self.latest_overlay_jpeg = overlay_jpg

        # Cropped stream: warp every call using cached M
        if self._M_img_to_crop is None:
            self.latest_cropped_jpeg = None
        else:
            warped = cv2.warpPerspective(
                frame_bgr,
                self._M_img_to_crop,
                (self.cfg.output_width, self.cfg.output_height),
            )

            # Draw transformed boxes + arrows in cropped space as well
            for mid, m in markers.items():
                pts = m.corners.reshape(-1, 1, 2).astype(np.float32)
                pts_w = cv2.perspectiveTransform(pts, self._M_img_to_crop).astype(int)
                cv2.polylines(warped, [pts_w], isClosed=True, color=(0, 255, 0), thickness=self.cfg.box_thickness)

                o = m.corners[3].reshape(1, 1, 2).astype(np.float32)
                tl = m.corners[0].reshape(1, 1, 2).astype(np.float32)
                o_w = cv2.perspectiveTransform(o, self._M_img_to_crop)[0][0].astype(int)
                tl_w = cv2.perspectiveTransform(tl, self._M_img_to_crop)[0][0].astype(int)
                cv2.arrowedLine(
                    warped,
                    (int(o_w[0]), int(o_w[1])),
                    (int(tl_w[0]), int(tl_w[1])),
                    color=(0, 255, 0),
                    thickness=self.cfg.box_thickness,
                    tipLength=0.25,
                )

                if self.cfg.draw_ids:
                    c = np.array([[m.center]], dtype=np.float32)
                    c_w = cv2.perspectiveTransform(c, self._M_img_to_crop)[0][0]
                    cx, cy = int(c_w[0]), int(c_w[1])
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

        # System printouts (1 Hz)
        self._maybe_print_poses(markers)
