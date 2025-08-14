import logging
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field
import cv2
import numpy as np

class GStreamerCamera:
    def __init__(self, port=554):
        self.port = port
        self.pipeline = (
            "udpsrc port=554 caps=\"application/x-rtp, media=(string)video, "
            "clock-rate=(int)90000, encoding-name=(string)JPEG, payload=26\" ! "
            "rtpjpegdepay ! jpegdec ! videoconvert ! appsink"
        )

        self.video = None
        self.start()

    def start(self):
        """Initializes the GStreamer video stream."""
        if self.video:
            self.video.release()  # Ensure any previous instance is closed
        self.video = cv2.VideoCapture(self.pipeline, cv2.CAP_GSTREAMER)
        if not self.video.isOpened():
            logging.error("Failed to open GStreamer video stream.")
        else:
            ret, frame = self.video.read()
            if ret and frame is not None:
                logging.infor(f"Received frame: shape={frame.shape}")
            else:
                logging.warning("Stream opened but no frame received.")

    def get_frame(self):
        """Reads a frame from the video stream."""
        if self.video and self.video.isOpened():
            ret, frame = self.video.read()
            if ret:
                return frame
        return None

    def restart_stream(self):
        """Restarts the video stream if needed."""
        self.start()


# Create a global camera instance
# camera = GStreamerCamera()

# Everything else remains unchanged

class CameraManager:
    def __init__(self, port=554):
        self.port = port
        self.pipeline = f"udpsrc port={self.port} ! application/x-rtp, encoding-name=jpeg, payload=26 ! rtpjpegdepay ! jpegdec ! videoconvert ! appsink"
        self.video = None

    def start(self):
        # Initialize the video capture using GStreamer pipeline
        self.video = cv2.VideoCapture(self.pipeline, cv2.CAP_GSTREAMER)
        if not self.video.isOpened():
            logging.error("Failed to open GStreamer video stream.")
            logging.error(f"Failed to open GStreamer video stream on port {self.port}.\nPipeline: {self.pipeline}")
            sys.exit(1)

    def get_frame(self):
        if self.video is None or not self.video.isOpened():
            logging.debug("Stream not open, restarting stream")
            self.restart_stream()
        ret, frame = self.video.read()
        if ret:
            return frame
        logging.debug("Failed to get frame")
        return None

    def restart_stream(self):
        if self.video is not None:
            logging.debug("Re-initializing the video stream.")
            self.video.release()
        self.start()



@dataclass
class ProcessedMarker:
    id: int
    x: float
    y: float
    pixels: tuple[int, int]
    theta: float = 0

    def __str__(self):
        return f'ID: {self.id}: ({self.x:.2f}, {self.y:.2f}, {self.theta:.2f})'

@dataclass
class DrawingOptions:
    obstacle_presets: list = field(default_factory=lambda: ['01A', '01B', '02A', '02B', '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B'])
    otv_start_loc: int = 0
    mission_loc: int = 1
    randomization: str = '01A'
    otv_start_dir: float = -(math.pi / 2)
    draw_dest: bool = False
    draw_obstacles: bool = False
    draw_coordinate: bool = False
    aruco_markers: dict[int, ProcessedMarker] = field(default_factory=dict)
    first: bool = True
    H = None
    camera_matrix = None
    inverse_matrix: list = field(default_factory=list)

dr_op: DrawingOptions = DrawingOptions()

team_types: dict = {
    0: "CRASH_SITE",
    1: "DATA",
    2: "MATERIAL",
    3: "FIRE",
    4: "WATER",
    5: "SEED",
}

fake_esp_data: list = [
    {'name': 'Forrest\'s Team', 'mission': 'Data',
     'aruco': {'num': 2, 'visible': True, 'x': 1, 'y': 2, 'theta': 3.14 / 2}},
    {'name': 'Gary\'s Team', 'mission': 'Water',
     'aruco': {'num': 3, 'visible': False, 'x': None, 'y': None, 'theta': None}},
]

esp_data: list = []

local = 'local' in sys.argv

if local:
    camera = GStreamerCamera()
else:
    camera = CameraManager()
    camera.start()
