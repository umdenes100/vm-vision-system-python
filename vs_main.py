import logging
import threading
from old import vs_comm
import vs_gui
import vs_opencv
import random
import math

from communications import vs_ws_server, esp_server, client_server

logFormatter = logging.Formatter("[%(relativeCreated)d][%(threadName)-16.16s][%(levelname)-5.5s] %(message)s")
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
consoleHandler.setLevel(logging.DEBUG)
logger = logging.getLogger()
logger.addHandler(consoleHandler)

# processed_Marker class
class processed_Marker:
    def __init__(self, idd, x, y, theta):
        self.id = idd
        self.x = x
        self.y = y
        self.theta = theta


# arucomarker object, designed to keep track of the id and pixel coordinates of each marker
class Marker:
    def __init__(self, idd, corner1, corner2, corner3, corner4):
        self.id = idd[0]
        self.corner1 = corner1
        self.corner2 = corner2
        self.corner3 = corner3
        self.corner4 = corner4


class DrawingOptions:
    def __init__(self):
        self.obstacle_presets = ['01A', '01B', '02A', '02B', '10A', '10B', '12A', '12B', '20A', '20B', '21A', '21B']
        self.otv_start_loc = 0
        self.mission_loc = 1
        self.randomization = self.obstacle_presets[random.randrange(0, 12)]
        self.otv_start_dir = -(math.pi / 2)
        self.draw_dest = False
        self.draw_obstacles = False
        self.draw_coordinate = False
        self.aruco_markers = {}
        self.first = True
        self.H = []
        self.inverse_matrix = []


def main():
    # Main drawing_options object. Shared between many threads.
    drawing_options = DrawingOptions()
    connections = vs_comm.Connections()

    logging.debug("Starting main thread")

    # start communication servers
    threading.Thread(name='ESP Server', target=esp_server.start_server).start()
    threading.Thread(name='Client Server', target=client_server.start_server).start()
    # start image processing
    threading.Thread(name='image_processing', target=vs_opencv.start_image_processing, args=(connections, drawing_options))\
        .start()

    # main process will now continue to GUI
    vs_gui.start_gui(connections, drawing_options)

if __name__ == '__main__':
    main()
