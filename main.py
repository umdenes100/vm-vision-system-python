### Library Changes
# todo remove need to define RX and TX ports. It should be automatic if you get them reversed.

import logging

logging.basicConfig(format='[%(threadName)-16.16s] %(levelname)s: %(message)s', level=logging.DEBUG)
import sys
import threading
import time
import webbrowser
from components import singleton
me = singleton.SingleInstance()
logging.info("Starting main thread\n")

from components import data
from components.usb_reset import reset_usb
from components.communications import client_server, esp_server, jetson_server
from components.machinelearning import ml


log_requests = {
    'esp': True,
    'jetson': True,
    'client': False,
}

local = 'local' in sys.argv
no_gui = 'no_gui' in sys.argv
if not local:
    from components.visioncomponents import vs_opencv

if not no_gui:
    from components import vs_gui


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
    threading.Thread(name='ML Startup', target=ml.start_ml, daemon=True).start()
    # start image processing
    if not local:
        threading.Thread(name='image_processing', target=vs_opencv.start_image_processing, daemon=True).start()

    webbrowser.open('http://192.168.1.2:8080')

    # # main process will now continue to GUI
    if not no_gui:
        vs_gui.start_gui()
        while vs_gui.gui_is_running:
            # while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
    else:
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
    logging.info("Exiting")


if __name__ == '__main__':
    main()
