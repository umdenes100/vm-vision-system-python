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

    # Physical coordinates of the *origin* (bottom-left) of each corner marker
    arena_bl: Tuple[float, float] = (0.0, 0.0)
    arena_tl: Tuple[float, float] = (0.0, 2.0)
    arena_tr: Tuple[float, float] = (4.0, 2.0)
    arena_br: Tuple[float, float] = (4.0, 0.0)

    # Output crop size (pixels)
    output_width: int = 1000
    output_height: int = 500

    # How often to refresh crop/arena homography from markers 0-3 (seconds)
    crop_refresh_seconds: float = 600.0  # 10 minutes

    # Crop border tuning
    border_marker_fraction: float = 0.5
    vertical_padding_fraction: float = 0.01

    # JPEG quality
    overlay_jpeg_quality: int = 80
    crop_jpeg_quality: int = 75

    # Drawing
    box_thickness: int = 2
    arrow_thickness: int = 1  # thinner than boxes
    origin_box_thickness: int = 1  # hollow box thickness
    draw_ids: bool = True

    # Arena bounds (validity check)
    arena_x_min: float = 0.0
    arena_x_max: float = 4.0
    arena_y_min: float = 0.0
    arena_y_max: float = 2.0

    # Hollow origin box half size (pixels)
    origin_box_half_size_px: int = 5

    # System printouts
    seen_markers_print_period_s: float = 60.0


class ArenaProcessor:
    """
    - aruco.py discovers/localizes markers in pixel space
    - arena.py:
        * computes crop transform from corner markers (0-3)
        * computes image->arena mapping
        * provides marker poses (x,y,theta) in arena coords
        * draws green boxes, red arrow, red hollow origin box
    """

    def __init__(self, cfg: ArenaConfig):
        self.cfg = cfg

        # IDs like 257/467/522/697 require DICT_4X4_1000 (0..999)
        self.detector = ArucoDetector(dict_name="DICT_4X4_1000")

        self.latest_overlay_jpeg: Optional[bytes] = None
        self.latest_cropped_jpeg: Optional[bytes] = None

        self._M_img_to_crop: Optional[np.ndarray] = None
        self._H_img_to_arena: Optional[np.ndarray] = None
        self._last_xform_update_monotonic: float = 0.0

        # Latest detected IDs and latest computed poses
        self._seen_ids: set[int] = set()
        self._poses_arena: Dict[int, Tuple[float, float, float]] = {}

        self._last_seen_print_monotonic: float = 0.0

    # -------------------- Public accessors --------------------

    @property
    def seen_ids(self) -> set[int]:
        return set(self._seen_ids)

    @property
    def poses_arena(self) -> Dict[int, Tuple[float, float, float]]:
        """
        marker_id -> (x,y,theta) in arena coords.
        If marker is out of bounds OR no mapping, will be (-1,-1,-1) for that marker if present.
        """
        return dict(self._poses_arena)

    # -------------------- Internal helpers --------------------

    @staticmethod
    def _encode_jpeg(bgr: np.ndarray, quality: int) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else None

    @staticmethod
    def _marker_origin_px(m: ArucoMarker) -> np.ndarray:
        # Bottom-left corner is origin (OpenCV order TL,TR,BR,BL => index 3 is BL)
        return m.corners[3].astype(np.float32)

    @staticmethod
    def _marker_topleft_px(m: ArucoMarker) -> np.ndarray:
        return m.corners[0].astype(np.float32)

    def _draw_origin_hollow_box(self, img: np.ndarray, origin_xy: Tuple[int, int]) -> None:
        hs = int(self.cfg.origin_box_half_size_px)
        x, y = int(origin_xy[0]), int(origin_xy[1])
        cv2.rectangle(
            img,
            (x - hs, y - hs),
            (x + hs, y + hs),
            color=(0, 0, 255),  # red (BGR)
            thickness=int(self.cfg.origin_box_thickness),
        )

    def _draw_marker_boxes_arrows_origins(self, img: np.ndarray, markers: Dict[int, ArucoMarker]) -> None:
        for mid, m in markers.items():
            pts = m.corners.astype(int).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], isClosed=True, color=(0, 255, 0), thickness=int(self.cfg.box_thickness))

            # Arrow: origin (BL) -> top-left (left edge) in RED, thinner
            o = m.corners[3].astype(int)
            tl = m.corners[0].astype(int)
            cv2.arrowedLine(
                img,
                tuple(o),
                tuple(tl),
                color=(0, 0, 255),
                thickness=int(self.cfg.arrow_thickness),
                tipLength=0.25,
            )

            # Hollow red box at the origin reference point
            self._draw_origin_hollow_box(img, (int(o[0]), int(o[1])))

            if self.cfg.draw_ids:
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
        IMPORTANT: Point order is always TL, TR, BR, BL to avoid rotation/twist.
        """
        bl = markers[self.cfg.id_bl]
        tl = markers[self.cfg.id_tl]
        tr = markers[self.cfg.id_tr]
        br = markers[self.cfg.id_br]

        # Arena mapping: use marker origin (bottom-left corner) points in TL,TR,BR,BL order
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

        # Crop mapping: use outer corners in TL,TR,BR,BL order
        def outer_corner(m: ArucoMarker, which: str) -> np.ndarray:
            c = m.corners  # TL,TR,BR,BL
            return {"tl": c[0], "tr": c[1], "br": c[2], "bl": c[3]}[which]

        src_crop = np.array(
            [
                outer_corner(tl, "tl"),
                outer_corner(tr, "tr"),
                outer_corner(br, "br"),
                outer_corner(bl, "bl"),
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

        self._M_img_to_crop = cv2.getPerspectiveTransform(src_crop, dst_crop)
        self._H_img_to_arena = cv2.getPerspectiveTransform(src_arena, dst_arena)

    def _maybe_refresh_transforms(self, markers: Dict[int, ArucoMarker]) -> None:
        if not self._have_corner_markers(markers):
            return

        now = time.monotonic()
        if self._M_img_to_crop is not None and (now - self._last_xform_update_monotonic) < float(self.cfg.crop_refresh_seconds):
            return

        self._compute_transforms_from_corners(markers)
        self._last_xform_update_monotonic = now

    def _transform_point(self, H: np.ndarray, p: np.ndarray) -> Tuple[float, float]:
        pts = np.array([[p]], dtype=np.float32)
        out = cv2.perspectiveTransform(pts, H)[0][0]
        return float(out[0]), float(out[1])

    def _marker_pose_arena(self, m: ArucoMarker) -> Tuple[float, float, float]:
        """
        Returns (x,y,theta) in arena coords.
        If out of bounds or no mapping: (-1,-1,-1)
        """
        if self._H_img_to_arena is None:
            return -1.0, -1.0, -1.0

        o_px = self._marker_origin_px(m)
        tl_px = self._marker_topleft_px(m)

        ox, oy = self._transform_point(self._H_img_to_arena, o_px)

        # Bounds check: if out of arena range => -1s
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

    def _maybe_print_seen_markers(self) -> None:
        now = time.monotonic()
        if (now - self._last_seen_print_monotonic) < float(self.cfg.seen_markers_print_period_s):
            return
        self._last_seen_print_monotonic = now

        ids = sorted(self._seen_ids)
        if not ids:
            web_info("Seen markers: none")
        else:
            web_info("Seen markers: " + ", ".join(str(i) for i in ids))

    # -------------------- Main processing --------------------

    def process_bgr(self, frame_bgr: np.ndarray) -> None:
        markers = self.detector.detect(frame_bgr)
        self._seen_ids = set(markers.keys())

        # Refresh transforms (stable)
        self._maybe_refresh_transforms(markers)

        # Update pose cache for all seen markers
        poses: Dict[int, Tuple[float, float, float]] = {}
        for mid, m in markers.items():
            poses[mid] = self._marker_pose_arena(m)
        self._poses_arena = poses

        # Full overlay
        overlay = frame_bgr.copy()
        self._draw_marker_boxes_arrows_origins(overlay, markers)
        overlay_jpg = self._encode_jpeg(overlay, self.cfg.overlay_jpeg_quality)
        if overlay_jpg is not None:
            self.latest_overlay_jpeg = overlay_jpg

        # Cropped overlay (warp every call using cached M)
        if self._M_img_to_crop is None:
            self.latest_cropped_jpeg = None
        else:
            warped = cv2.warpPerspective(
                frame_bgr,
                self._M_img_to_crop,
                (self.cfg.output_width, self.cfg.output_height),
            )

            # Draw overlays in cropped space by transforming points
            M = self._M_img_to_crop

            for mid, m in markers.items():
                pts = m.corners.reshape(-1, 1, 2).astype(np.float32)
                pts_w = cv2.perspectiveTransform(pts, M).astype(int)
                cv2.polylines(warped, [pts_w], True, (0, 255, 0), int(self.cfg.box_thickness))

                o = m.corners[3].reshape(1, 1, 2).astype(np.float32)
                tl = m.corners[0].reshape(1, 1, 2).astype(np.float32)
                o_w = cv2.perspectiveTransform(o, M)[0][0].astype(int)
                tl_w = cv2.perspectiveTransform(tl, M)[0][0].astype(int)

                cv2.arrowedLine(
                    warped,
                    (int(o_w[0]), int(o_w[1])),
                    (int(tl_w[0]), int(tl_w[1])),
                    (0, 0, 255),
                    int(self.cfg.arrow_thickness),
                    tipLength=0.25,
                )

                self._draw_origin_hollow_box(warped, (int(o_w[0]), int(o_w[1])))

                if self.cfg.draw_ids:
                    c = np.array([[m.center]], dtype=np.float32)
                    c_w = cv2.perspectiveTransform(c, M)[0][0]
                    cx, cy = int(c_w[0]), int(c_w[1])
                    cv2.putText(warped, str(mid), (cx + 6, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

            cropped_jpg = self._encode_jpeg(warped, self.cfg.crop_jpeg_quality)
            if cropped_jpg is not None:
                self.latest_cropped_jpeg = cropped_jpg

        # 60-second system printout of seen markers
        self._maybe_print_seen_markers()
