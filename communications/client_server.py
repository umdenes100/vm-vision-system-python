import http.server
import json
import logging
import threading

from websocket_server import WebsocketServer
from http.server import ThreadingHTTPServer

import data

ws_server: WebsocketServer
static_server: ThreadingHTTPServer


# Called for every client connecting (after handshake)
def new_client(client, server):
    logging.debug("New web client connected. and was given id %d" % client['id'])
    server.send_message_to_all(json.dumps({'type': 'data', 'data': data.fake_esp_data}))


# Called for every client disconnecting
def client_left(client, _):
    print("Client(%d) disconnected" % client['id'])


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
    if ws_server is None:
        logging.error('You tried to send a message before the ws_server is initialized.')
        return
    ws_server.send_message_to_all(json.dumps({'type': 'print', 'team': team_name, 'data': message}))


class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        self.path = '/static' + self.path
        return http.server.SimpleHTTPRequestHandler.do_GET(self)


def start_server():
    global ws_server, static_server
    ws_server = WebsocketServer(port=9000)
    ws_server.set_fn_new_client(new_client)
    ws_server.set_fn_client_left(client_left)
    ws_server.set_fn_message_received(message_received)
    logging.debug(f'Starting client ws_server on port {ws_server.port:d}')
    threading.Thread(target=ws_server.run_forever, daemon=True).start()

    server_address = ('', 8000)
    static_server = ThreadingHTTPServer(server_address, MyHttpRequestHandler)
    logging.debug(f'Starting client static_server on port http://localhost:{static_server.server_port:d}')
    static_server.serve_forever()
    # threading.Thread(target=static_server.serve_forever, daemon=True).start()

