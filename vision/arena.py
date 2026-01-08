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

    # Arena bounds (for validity check)
    arena_x_min: float = 0.0
    arena_x_max: float = 4.0
    arena_y_min: float = 0.0
    arena_y_max: float = 2.0

    # Origin marker point visualization (red box)
    origin_box_half_size_px: int = 4  # half-size of the red square (pixels)


class ArenaProcessor:
    """Detect markers, draw overlays, compute a stable crop, and map marker pose to arena coords."""

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

    def _draw_origin_box(self, img: np.ndarray, origin_xy: Tuple[int, int]) -> None:
        hs = int(self.cfg.origin_box_half_size_px)
        x, y = int(origin_xy[0]), int(origin_xy[1])
        cv2.rectangle(
            img,
            (x - hs, y - hs),
            (x + hs, y + hs),
            color=(0, 0, 255),  # red (BGR)
            thickness=-1,
        )

    def _draw_marker_boxes_arrows_origins(
        self,
        img: np.ndarray,
        markers: Dict[int, ArucoMarker],
        thickness: int,
        draw_ids: bool,
    ) -> None:
        for mid, m in markers.items():
            pts = m.corners.astype(int).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], isClosed=True, color=(0, 255, 0), thickness=thickness)

            # Arrow: from origin (bottom-left) to top-left (along left edge) in RED
            o = m.corners[3].astype(int)
            tl = m.corners[0].astype(int)
            cv2.arrowedLine(img, tuple(o), tuple(tl), color=(0, 0, 255), thickness=thickness, tipLength=0.25)

            # Red box at the origin point used for position reference
            self._draw_origin_box(img, (int(o[0]), int(o[1])))

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
        """
        IMPORTANT: All perspective transforms use consistent point order:
          TL, TR, BR, BL
        """
        bl = markers[self.cfg.id_bl]
        tl = markers[self.cfg.id_tl]
        tr = markers[self.cfg.id_tr]
        br = markers[self.cfg.id_br]

        # Arena mapping uses marker origin (bottom-left) points, in TL, TR, BR, BL order.
        src_arena = np.array(
            [
                self._marker_origin_px(tl),  # TL
                self._marker_origin_px(tr),  # TR
                self._marker_origin_px(br),  # BR
                self._marker_origin_px(bl),  # BL
            ],
            dtype=np.float32,
        )

        dst_arena = np.array(
            [
                self.cfg.arena_tl,  # (0,2)
                self.cfg.arena_tr,  # (4,2)
                self.cfg.arena_br,  # (4,0)
                self.cfg.arena_bl,  # (0,0)
            ],
            dtype=np.float32,
        )

        # Crop transform uses outer boundary points in TL, TR, BR, BL order.
        def outer_corner(m: ArucoMarker, which: str) -> np.ndarray:
            c = m.corners  # TL, TR, BR, BL
            if which == "tl":
                return c[0]
            if which == "tr":
                return c[1]
            if which == "br":
                return c[2]
            if which == "bl":
                return c[3]
            raise ValueError(which)

        src_crop = np.array(
            [
                outer_corner(tl, "tl"),  # TL
                outer_corner(tr, "tr"),  # TR
                outer_corner(br, "br"),  # BR
                outer_corner(bl, "bl"),  # BL
            ],
            dtype=np.float32,
        )

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
                [0, 0],  # TL
                [self.cfg.output_width - 1, 0],  # TR
                [self.cfg.output_width - 1, self.cfg.output_height - 1],  # BR
                [0, self.cfg.output_height - 1],  # BL
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

        # Bounds check: if out of arena range, return -1s
        if (
            ox < self.cfg.arena_x_min
            or ox > self.cfg.arena_x_max
            or oy < self.cfg.arena_y_min
            or oy > self.cfg.arena_y_max
        ):
            return -1.0, -1.0, -1.0

        tlx, tly = self._transform_point(self._H_img_to_arena, tl_px)
        vx = tlx - ox
        vy = tly - oy

        # Theta in radians: 0 along +x, +pi/2 along +y, -pi/2 along -y
        theta = math.atan2(vy, vx)
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

        corner_ids = {self.cfg.id_bl, self.cfg.id_tl, self.cfg.id_tr, self.cfg.id_br}
        ids = [i for i in sorted(markers.keys()) if i not in corner_ids]

        if not ids:
            web_info("Markers: none (non-corner)")
            return

        web_info(f"Markers ({len(ids)}): " + ", ".join(str(i) for i in ids))
        for mid in ids:
            pose = self._marker_pose_arena(markers[mid])
            if pose is None:
                continue
            x, y, th = pose
            web_info(f"ID {mid:>4}: x={x:7.3f}, y={y:7.3f}, theta={th: .6f} rad")

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        markers = self.detector.detect(frame_bgr)

        # Refresh transforms (stable crop/arena mapping)
        self._maybe_refresh_transforms(markers)

        # Overlay: full frame
        overlay = frame_bgr.copy()
        self._draw_marker_boxes_arrows_origins(overlay, markers, self.cfg.box_thickness, self.cfg.draw_ids)
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

            # Draw transformed boxes + arrows + origin box in cropped space
            for mid, m in markers.items():
                pts = m.corners.reshape(-1, 1, 2).astype(np.float32)
                pts_w = cv2.perspectiveTransform(pts, self._M_img_to_crop).astype(int)
                cv2.polylines(warped, [pts_w], isClosed=True, color=(0, 255, 0), thickness=self.cfg.box_thickness)

                # Arrow in red from origin to top-left
                o = m.corners[3].reshape(1, 1, 2).astype(np.float32)
                tl = m.corners[0].reshape(1, 1, 2).astype(np.float32)
                o_w = cv2.perspectiveTransform(o, self._M_img_to_crop)[0][0].astype(int)
                tl_w = cv2.perspectiveTransform(tl, self._M_img_to_crop)[0][0].astype(int)

                cv2.arrowedLine(
                    warped,
                    (int(o_w[0]), int(o_w[1])),
                    (int(tl_w[0]), int(tl_w[1])),
                    color=(0, 0, 255),
                    thickness=self.cfg.box_thickness,
                    tipLength=0.25,
                )

                # Red origin reference box
                self._draw_origin_box(warped, (int(o_w[0]), int(o_w[1])))

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
