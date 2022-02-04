import threading
from _thread import *
from vs_comm import *
from vs_gui import *
from vs_opencv import *

def main():
    connections = Connections()

    # start communication thread
    start_new_thread(start_communication, (connections, ))

    # start image processing
    start_new_thread(start_image_processing, (connections, ))

    # main process will now continue to GUI
    start_gui(connections)

if __name__ == '__main__':
    main()
