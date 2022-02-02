import threading
from _thread import *
from vs_comm import *  
from vs_gui import * 

def main():
    # start communication thread
    start_new_thread(start_communication)

    # start gui thread
    start_new_thread(start_gui)

    # main process will now continue to opencv stuff
    start_image_processing() 

if __name__ == '__main__':
    main()
