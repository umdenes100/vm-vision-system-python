# todo timeout if no flush sequence recieved
# todo error list of text.

### Library Changes
# todo remove mission site location.
# todo change library from Software Serial to AltSoftwareSerial to allow for higher baud rates.
# todo Upgrade baud rate to higher rate
# todo add a "wait for Vision System"
# todo remove need to define RX and TX ports. It should be automatic if you get them reversed.

import logging

import data

logging.basicConfig(format='[%(threadName)-16.16s]%(levelname)s:%(message)s', level=logging.DEBUG)

import sys
import threading
import time
import webbrowser

import singleton
from usb_reset import reset_usb


logging.info("Starting main thread\n")
me = singleton.SingleInstance()

log_requests = {
    'esp': True,
    'jetson': True,
    'client': False,
}

from communications import esp_server, client_server, jetson_server

local = 'local' in sys.argv

if not local:
    import vs_opencv
    import vs_gui


def main():
    if not local:
        client_server.usb_results = reset_usb()
    data.camera.begin()
    time.sleep(1)
    logging.debug("Starting main thread")
    # Main drawing_options object. Shared between many threads.
    # start communication servers
    threading.Thread(name='ESP Server', target=esp_server.start_server, daemon=True).start()
    threading.Thread(name='Client Server', target=client_server.start_server, daemon=True).start()
    threading.Thread(name='Jetson Server', target=jetson_server.start_server, daemon=True).start()
    # start image processing
    if not local:
        threading.Thread(name='image_processing', target=vs_opencv.start_image_processing, daemon=True).start()

    webbrowser.open('http://192.168.1.2:8080')

    # # main process will now continue to GUI
    vs_gui.start_gui()
    while vs_gui.gui_is_running:
    # while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break
    logging.info("Exiting")


if __name__ == '__main__':
    main()
