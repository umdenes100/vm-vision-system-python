import os

# If running windows
if os.name != 'nt':
    import cv2
from subprocess import Popen, PIPE, STDOUT


# Ok, so we need a way to store the connections from the esp ws_server and the client ws_server.
# It needs to be queryable.

class CameraManager:
    def __init__(self):
        # grab an actual camera as initial camera
        p = Popen('ls -1 /dev/video*', stdout=PIPE, stderr=STDOUT, shell=True)
        self.camera_num = p.communicate()[0].decode().split('\n')[0][-1]
        try:
            self.video = cv2.VideoCapture(int(self.camera_num), cv2.CAP_V4L2)
        except Exception as e:
            print(e)

        self.video.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.video.set(cv2.CAP_PROP_FPS, 30.0)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1920.0)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080.0)

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
                print(f'camera set to {num} in class')
                self.video = video
                self.camera_num = num
        except Exception as e:
            print(f'EXCEPTION: {e}')

    def get_camera(self):
        return self.video


fake_esp_data = [
    {'name': 'Forrest\'s Team', 'mission': 'Data',
     'aruco': {'num': 2, 'visible': True}},
    {'name': 'Gary\'s Team', 'mission': 'Water',
     'aruco': {'num': 3, 'visible': False}},
    {'name': 'Yo mama\'s Team (boom roasted)', 'mission': 'get shredded',
     'aruco': {'num': 4, 'visible': True}},
]

# camera: CameraManager = CameraManager()
