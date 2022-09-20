import json
import logging
import threading

from websocket_server import WebsocketServer

server: WebsocketServer


# Called for every client connecting (after handshake)
def new_client(client, server):
    logging.debug("New web client connected. and was given id %d" % client['id'])
    server.send_message_to_all(json.dumps({'type': 'data', 'data': fake_esp_data}))


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


# Called when the server needs to send a print message associated with a team.
def send_print_message(team_name, message):
    if server is None:
        logging.error('You tried to send a message before the server is initialized.')
        return
    server.send_message_to_all(json.dumps({'type': 'print', 'team': team_name, 'data': message}))


def start_server():
    global server
    server = WebsocketServer(port=9000)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    logging.debug(f'Starting client server on port {server.port:d}')
    threading.Thread(target=server.run_forever).start()
