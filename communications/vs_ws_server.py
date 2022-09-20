import json
import logging
import threading
import time

from websocket_server import WebsocketServer


# Called for every client connecting (after handshake)
def new_client(client, _):
    logging.debug("New web client connected. and was given id %d" % client['id'])
    server.send_message_to_all(json.dumps({'type': 'data', 'data': fake_esp_data}))


# Called for every client disconnecting
def client_left(client, server):
    print("Client(%d) disconnected" % client['id'])


# Called when a client sends a message
def message_received(client, server, message):
    message = json.loads(message)
    if message['type'] == 'register':
        logging.debug('register that baddie')
    if len(message) > 200:
        message = message[:200] + '..'
    print("Client(%d) said: %s" % (client['id'], message))




def send_dummy_prints():
    while True:
        for team in fake_esp_data:
            team = team['name']
            time.sleep(1)
            send_print_message(team, '1'+team+'\n')
            time.sleep(1)
            send_print_message(team, '2'+team+'\n')
            time.sleep(1)
            send_print_message(team, '3'+team+'\n')
            time.sleep(1)
            send_print_message(team, '4'+team+'\n')
            time.sleep(1)
            send_print_message(team, '5'+team+'\n')

def send_dummy_teams():
    while True:
        time.sleep(5)
        server.send_message_to_all(json.dumps({'type': 'data', 'data': fake_esp_data}))


if __name__ == '__main__':

    create_server()

    threading.Thread(target=create_server, args=(9000, None, new_client, )).start()
    threading.Thread(target=start_esp_server).start()
    start_server()
