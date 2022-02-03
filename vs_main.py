import threading
from _thread import *
import vs_comm  
import vs_gui
import vs_opencv

def main():
    # start communication thread
    start_new_thread(vs_comm.start_communication, ())

    # start image processing
    start_new_thread(vs_opencv.start_image_processing, ())

    # main process will now continue to GUI
    vs_gui.start_gui()

if __name__ == '__main__':
    main()
