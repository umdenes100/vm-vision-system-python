# todo timeout if no flush sequence recieved
# todo error list of text.

### Library Changes
# todo remove need for 3 second delay in VisionSystemClient.cpp
# todo remove mission site location.
# todo change library from Software Serial to AltSoftwareSerial to allow for higher baud rates.
# todo Upgrade baud rate to higher rate
# todo add a "wait for Vision System"
# todo instead of waiting for 3 seconds, just wait for a response from the ESP module.
# todo remove need to define RX and TX ports. It should be automatic if you get them reversed.
# todo if the port is not established, fail the requests like updateLocation
import logging
import sys
import threading
import time
import webbrowser

import vs_gui
from usb_reset import reset_usb

logging.basicConfig(format='[%(threadName)-16.16s]%(levelname)s:%(message)s', level=logging.DEBUG)

logging.info("Starting main thread\n")

from communications import esp_server, client_server

local = 'local' in sys.argv

if not local:
    import vs_opencv


def main():
    client_server.usb_results = reset_usb()
    time.sleep(1)
    logging.debug("Starting main thread")
    # Main drawing_options object. Shared between many threads.
    # start communication servers
    threading.Thread(name='ESP Server', target=esp_server.start_server, daemon=True).start()
    threading.Thread(name='Client Server', target=client_server.start_server, daemon=True).start()
    # start image processing
    if not local:
        threading.Thread(name='image_processing', target=vs_opencv.start_image_processing, daemon=True).start()

    webbrowser.open('http://192.168.1.2:8080')

    # # main process will now continue to GUI
    vs_gui.start_gui()
    while vs_gui.gui_is_running:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break
    logging.info("Exiting")


if __name__ == '__main__':
    main()
