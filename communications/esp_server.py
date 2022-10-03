import logging
import threading

from websocket_server import WebsocketServer

ws_server: WebsocketServer


# Called for every client connecting (after handshake)
def new_client(client, server: WebsocketServer):
    logging.debug("New web client connected. and was given id %d" % client['id'])
    server.send_message(client, 'benis')


# Called for every client disconnecting
def client_left(client, _):
    print("Client(%d) disconnected" % client['id'])


# Called when a client sends a message
def message_received(client, server: WebsocketServer, message):
    print(message)
    server.send_message(client, 'penis')
    print("Client(%d) said: %s" % (client['id'], message))
    return


def send_to_all(message):
    ws_server.send_message_to_all(message)


def start_server():
    logging.info('please dear god print')
    global ws_server
    server = WebsocketServer(port=7755)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    logging.debug(f'Starting client server on port {server.port:d}')
    threading.Thread(target=server.run_forever).start()
