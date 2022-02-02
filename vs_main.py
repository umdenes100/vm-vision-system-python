import threading
from _thread import *
from vs_comm import *  
from vs_gui import * 

def main():
    # TODO - start communication
    start_new_thread(start_communication)

    # TODO - start gui
    start_gui()

if __name__ == '__main__':
    main()
