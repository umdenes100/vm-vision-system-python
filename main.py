import logging
import sys
import threading
import time
import webbrowser
from components import singleton

print(">>> Vision System Starting")
me = singleton.SingleInstance()

from components import data
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

# Only import GUI components if no_gui flag is not set
if not no_gui:
    from components import vs_gui


def main():
    time.sleep(1)
    logging.debug("Starting main thread")

    # Start communication servers
    #threading.Thread(name='ESP Server', target=esp_server.start_server, daemon=True).start()
    ws_server = esp_server.start_server()
    if ws_server is None:
        print(">>> ESP Server failed to start!")
        return
    threading.Thread(name='Send Locations',target=esp_server.send_locations,args=(ws_server,),daemon=True).start()
    print(">>> ESP Server Started")
    threading.Thread(name='Client Server', target=client_server.start_server, daemon=True).start()
    print(">>> Client Server Started")
    threading.Thread(name='Jetson Server', target=jetson_server.start_server, daemon=True).start()
    print(">>> Jetson Server Started")
    threading.Thread(name='ML Startup', target=ml.start_ml, daemon=True).start()
    print(">>> ML Startup Started")

    # Start image processing with the GStreamer-based UDP stream
    if not local:
        threading.Thread(name='image_processing', target=vs_opencv.start_image_processing, daemon=True).start()

    webbrowser.open('http://10.112.9.33:8080')
    print(">>> ALL SYSTEMS OPERATIONAL")

    # Main loop for GUI or headless mode
    if not no_gui:
        vs_gui.start_gui()  # Start GUI only if no_gui flag is not set
        while vs_gui.gui_is_running:
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
    print(">>> Exiting")


if __name__ == '__main__':
    main()
