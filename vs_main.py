import threading
from _thread import *
from vs_comm import *
from vs_gui import *
from vs_opencv import *
import random
import math

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
        self.randomization = self.obstacle_presets[random.randrange(0,12)]
        self.otv_start_dir = -(math.pi / 2)
        self.draw_dest = False
        self.draw_obstacles = False
        self.draw_coordinate = False
        self.aruco_markers = {}
        self.first = True
        self.H = []
        self.inverse_matrix = []

def main():
    dr_op = DrawingOptions()
    connections = Connections()

    open('errors.txt', 'w').write('\n')
    
    # start communication thread
    start_new_thread(start_communication, (connections, dr_op, ))

    # start image processing
    start_new_thread(start_image_processing, (connections, dr_op))

    # main process will now continue to GUI
    start_gui(connections, dr_op)

if __name__ == '__main__':
    main()
