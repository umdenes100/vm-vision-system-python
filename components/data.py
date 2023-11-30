import logging
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field

# If running windows
if os.name != 'nt':
    import cv2
from subprocess import Popen, PIPE, STDOUT


# Ok, so we need a way to store the connections from the esp ws_server and the client ws_server.
# It needs to be queryable.

class CameraManager:
    def __init__(self):
        self.video = None
        self.camera_num = None

    def set_cam(self, num):
        try:
            self.video.release()
            p = Popen(["v4l2-ctl", f"--device=/dev/video{num}", "--all"], stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, err = p.communicate()
            if "brightness" in output.decode():
                video = cv2.VideoCapture(num, cv2.CAP_V4L2)
                video.set(cv2.CAP_PROP_FOURCC,
                          cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))  # depends on fourcc available camera
                video.set(cv2.CAP_PROP_FPS, 30.0)
                video.set(cv2.CAP_PROP_FRAME_WIDTH, 1920.0)  # supported widths: 1920, 1280, 960
                video.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080.0)  # supported heights: 1080, 720, 540
                video.set(cv2.CAP_PROP_FPS, 30.0)  # supported FPS: 30, 15
                print(f'camera set to {num}')
                self.video = video
                self.camera_num = int(num)
        except KeyboardInterrupt:
            exit()
        except Exception as e:
            print(f'EXCEPTION: {e}')

    def get_camera(self):
        return self.video

    def restart_stream(self):
        self.video.release()
        self.video = cv2.VideoCapture(self.camera_num, cv2.CAP_V4L2)
        self.video.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.video.set(cv2.CAP_PROP_FPS, 30.0)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1920.0)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080.0)
        return self.video


    def begin(self):
        logging.debug("Camera Manager initialized")
        legit_cameras = []
        cameras = os.listdir('/dev/')
        cameras.sort()
        for c in cameras:
            if "video" in c:
                process = subprocess.Popen(['v4l2-ctl', f'--device=/dev/{c}', '--all'], stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                out, err = process.communicate()
                if b"Format Video Capture:" in out:
                    legit_cameras.append(c)
                    logging.debug(f'Found legit camera: {c}')

        if len(legit_cameras) == 2:
            logging.debug(f'length of legit_cameras is 2, picking {legit_cameras[1]}')
            self.camera_num = int(legit_cameras[1][-1])  # It is probably the second camera
        elif len(legit_cameras) == 1:
            logging.debug(f'length of legit_cameras is 1, picking {legit_cameras[0]}')
            self.camera_num = int(legit_cameras[0][-1])  # otherwise pick the first one
        try:
            self.video = cv2.VideoCapture(int(self.camera_num), cv2.CAP_V4L2)
        except Exception as e:
            print(e)

        self.video.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.video.set(cv2.CAP_PROP_FPS, 30.0)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1920.0)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080.0)


# ProcessedMarker class
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
    obstacle_presets: list = field(
        default_factory=lambda: ['01A', '01B', '02A', '02B', '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B'])
    otv_start_loc: int = 0
    mission_loc: int = 1
    randomization: str = '01A'
    otv_start_dir: float = -(math.pi / 2)
    draw_dest: bool = False
    draw_obstacles: bool = False
    draw_arrows: bool = True
    draw_text: bool = True
    draw_coordinate: bool = False
    aruco_markers: dict[int, ProcessedMarker] = field(default_factory=dict)
    first: bool = True
    H = None
    camera_matrix = None
    inverse_matrix: list = field(default_factory=list)

    # self.randomization = self.obstacle_presets[random.randrange(0, 12)]


dr_op: DrawingOptions = DrawingOptions()

team_types: dict = {
    0: "CRASH_SITE",
    1: "DATA",
    2: "MATERIAL",
    3: "FIRE",
    4: "WATER",
    5: "MACHINE_LEARNING",
}

fake_esp_data: list = [
    {'name': 'Forrest\'s Team', 'mission': 'Data',
     'aruco': {'num': 2, 'visible': True, 'x': 1, 'y': 2, 'theta': 3.14 / 2}},
    {'name': 'Gary\'s Team', 'mission': 'Water',
     'aruco': {'num': 3, 'visible': False, 'x': None, 'y': None, 'theta': None}},
]

esp_data: list = []

local = 'local' in sys.argv
if not local:
    camera: CameraManager = CameraManager()
