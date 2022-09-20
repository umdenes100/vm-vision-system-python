import json
import logging
import threading

from websocket_server import WebsocketServer

server: WebsocketServer


# Called for every client connecting (after handshake)
def new_client(client, server):
    logging.debug("New web client connected. and was given id %d" % client['id'])


# Called for every client disconnecting
def client_left(client, _):
    print("Client(%d) disconnected" % client['id'])


# Called when a client sends a message
def message_received(client, _, message):
    print(message)
    return
    message = json.loads(message)
    if message['type'] == 'register':
        logging.debug('register that baddie')
    if len(message) > 200:
        message = message[:200] + '..'
    print("Client(%d) said: %s" % (client['id'], message))


def start_server():
    global server
    server = WebsocketServer(port=7755)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    logging.debug(f'Starting client server on port {server.port:d}')
    threading.Thread(target=server.run_forever).start()
