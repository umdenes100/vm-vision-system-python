import http.server
import json
import logging
import os
import struct
import sys
import threading
import time
from http.server import ThreadingHTTPServer

from websocket_server import WebsocketServer, WebSocketHandler, OPCODE_BINARY, FIN, PAYLOAD_LEN_EXT16, PAYLOAD_LEN_EXT64

import components.communications.esp_server

local = 'local' in sys.argv

ws_server: WebsocketServer
static_server: ThreadingHTTPServer

usb_results = None


# Called for every client connecting (after handshake)
def new_client(client, __):
    logging.debug("New WEB client connected.")
    jpegs = []
    for file in os.listdir('static'):
        if file.endswith('.jpg') or file.endswith('.jpeg') or file.endswith('.png') or file.endswith('.gif'):
            jpegs.append(file)
    print(jpegs)
    ws_server.send_message(client, json.dumps({'type': 'jpegs', 'data': jpegs}))
    send_error_message(usb_results if usb_results is not None else 'No USB results yet.')


# Called for every client disconnecting
def client_left(client, _):
    print(f"WEB Client({client['id']:d}) disconnected")


# Called when a client sends a message
def message_received(client, _, message):
    message = json.loads(message)
    if message['type'] == 'register':
        logging.debug('register that baddie')
    if len(message) > 200:
        message = message[:200] + '..'
    print("Client(%d) said: %s" % (client['id'], message))


# Called when the ws_server needs to send a print message associated with a team.
def send_print_message(team_name, message):
    """
    Sends a print message to the web client.
    :param team_name: The name of the team to say the message is on behalf of.
    :param message: The message (str)
    :return:
    """
    if ws_server is None:
        logging.error('You tried to send a message before the ws_server is initialized.')
        return
    ws_server.send_message_to_all(json.dumps({'type': 'print', 'team': team_name, 'data': message}))


def send_error_message(message: str):
    """
    Sends an error message to the web client.
    """
    if ws_server is None:
        return
    # logging.debug(f'Sending error message: {message}')
    ws_server.send_message_to_all(json.dumps({'type': 'error', 'data': message}))


# The way we send the static HTML page is with a simple HTTP server. We only server from the static folder. Very insecure.
class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        self.path = '/static' + self.path
        try:
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        except BrokenPipeError:
            logging.debug('Broken pipe error on GET request')


def start_server():
    global ws_server, static_server
    if local:
        host = sys.argv[sys.argv.index('host') + 1] if 'host' in sys.argv else 'localhost'
    else:
        host = '192.168.1.2'
    try:
        ws_server = WebsocketServer(host=host, port=9000)
    except OSError as e:
        if e.errno == 98:
            logging.error('Program is already running on this computer. Please close other instance.')
            exit(1)
    try:
        if ws_server is None:
            logging.error(
                'client_server -> ws_server is None. Did you make sure to set the network up correctly? (Assign static IP on wired connection) See readme.md')
            return
    except NameError:
        logging.error(
            'client_server -> ws_server is not defined. Did you make sure to set the network up correctly? (Assign static IP on wired connection) See readme.md')
        return
    ws_server.set_fn_new_client(new_client)
    ws_server.set_fn_client_left(client_left)
    ws_server.set_fn_message_received(message_received)
    logging.debug(f'Starting client ws_server on port {ws_server.port:d}')
    threading.Thread(target=ws_server.run_forever, daemon=True, name='Web WS Server').start()

    static_server = ThreadingHTTPServer((host, 8080), MyHttpRequestHandler)
    logging.debug(f'Starting client static_server on port http://{host}:{static_server.server_port:d}')
    threading.Thread(target=static_server.serve_forever, daemon=True, name='Web Static Server').start()

    while True:
        time.sleep(0.25)
        d = components.communications.esp_server.ws_server.clients

        d = list(filter(lambda c: 'teamName' in c, d))
        ws_server.send_message_to_all(
            json.dumps({'type': 'data', 'data': d}, default=lambda o: f"<<non-serializable: {type(o).__qualname__}>>"))


def send_frame(frame: bytes):
    # print(f'sending frame. Shape: {type(frame)}  Length: {len(frame)}')
    global ws_server
    # Since this is probably the most complicated code in this repo, I'll explain it in more depth.
    # Our dumbo library doesn't support binary frames out of the box. Note: This is pretty much copied with a few
    # modifications from the library itself. See https://github.com/Pithikos/python-websocket-server/blob/master/websocket_server/websocket_server.py#L371
    opcode = OPCODE_BINARY  # We are sending binary.
    header = bytearray()  # The binary header. Bytearray is basically bytes() but can be appended to.

    header.append(FIN | opcode)
    payload_length = len(frame)

    # Depending on the JPEG compression ratio (see the line calling cv2.imencode in vs_opencv.py) our image (1920*1080*3 = 6.2MB)
    # is compressed to around 70k bytes.
    if payload_length <= 125:  # Normal payload
        header.append(payload_length)
    elif 126 <= payload_length <= 65535:  # Extended payload.
        header.append(PAYLOAD_LEN_EXT16)
        header.extend(struct.pack(">H", payload_length))
    else:  # Huge extended payload. Max 18000 petabytes. (2^64 bytes) You'll never hit this limit.
        header.append(PAYLOAD_LEN_EXT64)
        header.extend(struct.pack(">Q", payload_length))

    for client in ws_server.clients:
        c = client['handler']
        assert isinstance(c, WebSocketHandler)

        with c._send_lock:
            c.request.send(header + frame)
