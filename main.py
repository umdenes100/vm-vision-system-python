import logging
import sys
import threading
import time
import webbrowser

from components import singleton
from components.communications import client_server, esp_server
from components.machinelearning import ml
from components.visioncomponents import vs_opencv

print(">>> Vision System Starting")
_ = singleton.SingleInstance()

# Flags
no_browser = 'no_browser' in sys.argv
no_vision = 'no_vision' in sys.argv
stream_port = 5000

# Optional: allow port override like: port=5001
for arg in sys.argv[1:]:
    if arg.startswith('port='):
        try:
            stream_port = int(arg.split('=', 1)[1])
        except ValueError:
            pass


def main():
    time.sleep(1)
    logging.debug("Starting main thread")

    # ESP websocket server (robot clients)
    ws_server = esp_server.start_server()
    if ws_server is None:
        print(">>> ESP Server failed to start!")
        return

    # Send locations periodically (only start ONE thread)
    threading.Thread(
        name='Send Locations',
        target=esp_server.send_locations,
        args=(ws_server,),
        daemon=True
    ).start()

    print(">>> ESP Server Started")

    # Browser client server (HTTP + websocket for video/telemetry)
    threading.Thread(name='Client Server', target=client_server.start_server, daemon=True).start()
    print(">>> Client Server Started")

    # ML subsystem
    threading.Thread(name='ML Startup', target=ml.start_ml, daemon=True).start()
    print(">>> ML Startup Started")

    # Vision loop (stream-only)
    if not no_vision:
        threading.Thread(
            name='image_processing',
            target=vs_opencv.start_image_processing,
            args=(stream_port,),
            daemon=True
        ).start()

    if not no_browser:
        # Keep existing behavior; update this if your host/IP changes.
        webbrowser.open('http://10.112.9.33:8080')

    print(">>> ALL SYSTEMS OPERATIONAL")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    print(">>> Exiting")


if __name__ == '__main__':
    main()
