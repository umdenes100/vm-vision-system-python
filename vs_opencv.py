# importing the necessary libraries
import cv2
import numpy as np
import vs_comm 

drawing_options = {'draw_dest': False, 'draw_obstacles': False, 'draw_coord': False, 
                   'otv_start_loc': 0, 'otv_start_dir_theta': 0, 'mission_loc': 1,
                   'randomization': {}}
aruco_markers = {}

def draw_on_frame(frame):
    # TODO - detect aruco markers
    # TODO - draw aruco markers
    # TODO - draw arena
    print("in progress...")
    return frame

def frame_capture(cap):
    # Loop until the end of the video
    if (cap.isOpened()):
        ret, frame = cap.read()
 
        # Display the resulting frame
        cv2.imshow('Frame', frame)

        # TODO - draw on image
        new_frame = draw_on_frame(frame)

        jpeg_bytes = cv2.imencode('.jpg', new_frame)[1]
        
        # send frame to each of the connections in the connection list in vs_comm.py
        vs_comm.send_frame(new_frame)
 
def start_image_processing():
    cap = cv2.VideoCapture(0)
    while 1:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')) # depends on fourcc available camera
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        #cap.set(cv2.CAP_PROP_FPS, 10) # maybe 5
        
        frame_capture(cap)
        cv2.waitKey(1) 
        # define q as the exit button
        #if cv2.waitKey() & 0xFF == ord('q'):
        #    break

    cap.release()
    cv2.destroyAllWindows()

