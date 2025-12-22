import logging
import math
from dataclasses import dataclass, field

import cv2


class StreamCamera:
    """Stream-only camera source.

    Frames are pulled from an H.264 RTP stream over UDP (default port 5000)
    using a low-latency GStreamer pipeline.
    """

    def __init__(self, port: int = 5000, latency_ms: int = 250):
        self.port = int(port)
        self.latency_ms = int(latency_ms)
        self.video = None

        # Mirrors the working gst-launch low-latency pipeline.
        self.pipeline = (
            f'udpsrc port={self.port} caps="application/x-rtp,media=(string)video,'
            'encoding-name=(string)H264,clock-rate=(int)90000,payload=(int)96" ! '
            f'rtpjitterbuffer latency={self.latency_ms} ! '
            'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
            'queue max-size-buffers=1 leaky=downstream ! '
            'video/x-raw,format=(string)BGR ! '
            'appsink sync=false drop=true max-buffers=1'
        )

    def start(self) -> None:
        """(Re)open the stream."""
        if self.video:
            try:
                self.video.release()
            except Exception:
                pass

        self.video = cv2.VideoCapture(self.pipeline, cv2.CAP_GSTREAMER)
        if not self.video.isOpened():
            logging.error("Failed to open GStreamer video stream (UDP port %s).", self.port)
            return

        # Prime the stream so we don't sit on an old preroll buffer.
        _ = self.video.read()
        _ok, _frame = self.video.read()

    def get_frame(self):
        """Read a frame. Returns None if unavailable."""
        if not self.video or not self.video.isOpened():
            return None
        ok, frame = self.video.read()
        return frame if ok else None

    def restart_stream(self) -> None:
        self.start()

    def release(self) -> None:
        if self.video:
            try:
                self.video.release()
            except Exception:
                pass
            self.video = None


@dataclass
class ProcessedMarker:
    id: int
    x: float
    y: float
    pixels: tuple[int, int]
    theta: float = 0.0

    def __str__(self) -> str:
        return f'ID: {self.id}: ({self.x:.2f}, {self.y:.2f}, {self.theta:.2f})'


@dataclass
class DrawingOptions:
    # NOTE: This file used to contain USB camera plumbing. It is intentionally
    # stream-only now; these options are still used by the vision pipeline.
    obstacle_presets: list = field(default_factory=lambda: [
        '00A', '00B', '01A', '01B', '02A', '02B',
        '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B'
    ])
    otv_start_loc: int = 0
    mission_loc: int = 1
    randomization: str = '01A'
    otv_start_dir: float = -(math.pi / 2)
    draw_dest: bool = False
    draw_obstacles: bool = False
    draw_coordinate: bool = False
    aruco_markers: dict[int, "ProcessedMarker"] = field(default_factory=dict)
    first: bool = True
    H = None
    camera_matrix = None
    inverse_matrix: list = field(default_factory=list)


# Global drawing/runtime options (used across modules)
dr_op = DrawingOptions()

# Team / mission data
teams: list[dict] = [
    {'name': "Alex's Team", 'mission': 'Sand',
     'aruco': {'num': 0, 'visible': False, 'x': None, 'y': None, 'theta': None}},
    {'name': "Damian's Team", 'mission': 'Sample',
     'aruco': {'num': 1, 'visible': False, 'x': None, 'y': None, 'theta': None}},
    {'name': "Forrest's Team", 'mission': 'Data',
     'aruco': {'num': 2, 'visible': True, 'x': 1, 'y': 2, 'theta': 3.14 / 2}},
    {'name': "Gary's Team", 'mission': 'Water',
     'aruco': {'num': 3, 'visible': False, 'x': None, 'y': None, 'theta': None}},
]

esp_data: list = []
