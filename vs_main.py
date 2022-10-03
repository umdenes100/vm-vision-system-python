import logging
#
# logging.basicConfig(level=logging.INFO,
#                     format='[%(relativeCreated)d][%(threadName)-16.16s][%(levelname)-5.5s] %(message)s')
import threading
import random
import math

logging.basicConfig(format='[%(threadName)-16.16s]%(levelname)s:%(message)s', level=logging.DEBUG)

from communications import esp_server, client_server

logging.info("Starting main thread\n")

# ProcessedMarker class
class ProcessedMarker:
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
    logging.debug("Starting main thread")
    # Main drawing_options object. Shared between many threads.
    # drawing_options = DrawingOptions()
    # start communication servers

    threading.Thread(name='ESP Server', target=esp_server.start_server, daemon=True).start()
    threading.Thread(name='Client Server', target=client_server.start_server, daemon=True).start()
    client_server.start_server()  # Returns
    # start image processing
    # threading.Thread(name='image_processing', target=vs_opencv.start_image_processing, args=(connections, drawing_options))\
    #     .start()
    #
    # # main process will now continue to GUI
    # vs_gui.start_gui(connections, drawing_options)


if __name__ == '__main__':
    main()
