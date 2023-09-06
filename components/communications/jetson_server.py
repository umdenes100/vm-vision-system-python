import json
import logging
import sys
import threading
import time

from websocket_server import WebsocketServer

from components.communications import client_server, esp_server
from components.communications.ping import ping

ws_server: WebsocketServer

local = 'local' in sys.argv

# Previous connections allows us to record the name of a team so when a jetson, we can inform the user whose jetson reconnects.
previous_connections: dict[str, str] = {}  # {'ip': 'cached name'}
# List of IPs that we have forcibly disconnected. We don't want to send an error message for these.
ignorable_disconnects: set[str] = set()


# Helper message to get the teams name to the best of our knowledge
def get_team_name(client):
    if 'teamName' in client:
        return client['teamName']
    if client['address'][0] in previous_connections:
        return '(Cached Name)' + previous_connections[client['address'][0]]
    return f'No Team Name (IP: {client["address"][0]})'


# Called for every client connecting (after handshake)
def new_client(client, server: WebsocketServer):
    logging.debug(f"New JETSON client connected and was given id {client['id']:d}")
    if client['address'][0] in previous_connections:
        client_server.send_error_message(
            f'Jetson with previous name {previous_connections[client["address"][0]]} reconnected... waiting for client initialization')
    else:
        client_server.send_error_message(f'New Jetson connected... waiting for client initialization')


# Called for every client disconnecting
def client_left(client, _):
    if client is not None:
        client_server.send_error_message(f'Jetson from team {get_team_name(client)} disconnected...')
    elif client['address'][0] not in ignorable_disconnects:
        logging.debug("Unknown Client disconnected... mysterious")
        client_server.send_error_message(f'Unknown Jetson disconnected... mysterious')
    ignorable_disconnects.discard(client['address'][0])


# Called when a Wi-Fi client sends a message
def message_received(client, server: WebsocketServer, message):
    if client is None:
        logging.debug(f'Unknown Jetson sent a message - {message}')
        return
    import main
    if main.log_requests['jetson']:
        logging.debug(f'Team: "{client.get("teamName") if client.get("teamName") else "No Team Name"}" sent message {message}')
    try:
        message = json.loads(message)
        if message is None:
            logging.debug(f'Jetson from team {get_team_name(client)} sent an empty message. (Could be ping...)')
            client_server.send_error_message(
                f'Jetson from team {get_team_name(client)} sent an invalid message.')
            return
    except json.JSONDecodeError:
        logging.debug(f'Invalid JSON: {message}')
        client_server.send_error_message(
            f'Jetson from team {get_team_name(client)} sent an invalid message.')
        return

    if message['op'] == 'begin':
        # Check to make sure the team name is unique
        if message['teamName'] in [get_team_name(c) for c in ws_server.clients if c != client]:
            client_server.send_error_message(
                f'Jetson tried to connect with team name {message["teamName"]}. It is already in use for another Jetson. Please choose a different name.')
            return
        client['teamName'] = message['teamName']
        previous_connections[client['address'][0]] = client['teamName']
        ws_server.send_message(client,
                               json.dumps({'op': 'status', 'status': 'OK'}))
        ignorable_disconnects.discard(client['address'][0])  # This client is now valid.
        client_server.send_error_message(f'Jetson from team {get_team_name(client)} client initialization complete.')
        logging.debug(f'Jetson from team {get_team_name(client)} client initialization complete.')
    if message['op'] == 'prediction_results':
        if 'teamName' not in client:
            client_server.send_error_message(
                f'Jetson {get_team_name(client)} tried to send prediction results before initialization.')
            logging.debug(
                f'Jetson {get_team_name(client)} tried to send prediction results before initialization.')
            return
        if 'prediction' not in message:
            client_server.send_error_message(
                f'Jetson {get_team_name(client)} tried to send prediction results without a prediction.')
            logging.debug(
                f'Jetson {get_team_name(client)} tried to send prediction results without a prediction.')
            return

        # Send the prediction to the esp
        esp_server.send_prediction(client['teamName'], message['prediction'])
        logging.debug(f'Jetson {get_team_name(client)} sent prediction results ({message["prediction"]}) to esp.')



def request_prediction(team_name, image_hex):
    # Find the client with the given team name
    for client in ws_server.clients:
        if 'teamName' in client and client['teamName'] == team_name:
            ws_server.send_message(client, json.dumps({'op': 'prediction_request', 'image': image_hex}))
            return True
    return False


def image_capture(team_name, image_hex, category):
    # Find the client with the given team name
    for client in ws_server.clients:
        if 'teamName' in client and client['teamName'] == team_name:
            ws_server.send_message(client, json.dumps({'op': 'image_capture', 'image': image_hex, 'category': category}))
            return True
    return False

# noinspection PyTypeChecker
def start_server():
    global ws_server
    ws_server = None
    try:
        if local:
            if 'host' in sys.argv:
                ws_server = WebsocketServer(port=7756, host=sys.argv[sys.argv.index('host') + 1])
            else:
                ws_server = WebsocketServer(port=7756)
        else:
            ws_server = WebsocketServer(host='192.168.1.2', port=7756)
    except OSError as e:
        if e.errno == 98:
            logging.error('Program is already running on this computer. Please close other instance.')
            exit(1)
    ws_server.set_fn_new_client(new_client)
    ws_server.set_fn_client_left(client_left)
    ws_server.set_fn_message_received(message_received)
    logging.debug(f'Starting client jetson_server on port {ws_server.port:d}')
    threading.Thread(target=ws_server.run_forever, name='Jetson WS Server').start()

    # We will ping all esp clients to make sure they haven't disconnected. Sadly, when ESP clients power off
    # unexpectedly, they do not fire the disconnect callback.
    def check_connection():
        while True:
            for client in ws_server.clients:
                if not ping(client['address'][0]):
                    logging.debug(f'Client {client["address"][0]} is not responding to ping. Disconnecting.')
                    ignorable_disconnects.add(client['address'][0])
                    # noinspection PyProtectedMember
                    ws_server._terminate_client_handler(client['handler'])
            time.sleep(1)

    threading.Thread(target=check_connection, daemon=True, name='Jetson Check Connection').start()
