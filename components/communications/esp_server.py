import json
import logging
import random
import sys
import threading
import time

from websocket_server import WebsocketServer

from components import data
from components.communications import client_server, jetson_server
from components.communications.ping import ping
from components.data import team_types, dr_op
from components.vs_mission import get_mission_message

ws_server: WebsocketServer

local = 'local' in sys.argv

# Previous connections allows us to record the name of a team so when a Wi-Fi module reconnects, we can inform the user whose module reconnects.
previous_connections: dict[str, str] = {}  # {'ip': 'cached name'}
# List of IPs that we have forcibly disconnected. We don't want to send an error message for these.
ignorable_disconnects: set[str] = set()

def once():
    # Get the line number and file where this function was called from
    import inspect
    frame = inspect.currentframe().f_back
    lineno = frame.f_lineno
    filename = frame.f_code.co_filename

    if not hasattr(once, 'called'):
        once.called = []
    if (filename, lineno) in once.called:
        return False
    once.called.append((filename, lineno))
    return True


# Helper message to get the teams name to the best of our knowledge
def get_team_name(client):
    if 'teamName' in client:
        return client['teamName']
    if client['address'][0] in previous_connections:
        return '(Cached Name)' + previous_connections[client['address'][0]]
    return f'No Team Name (IP: {client["address"][0]})'


# Called for every client connecting (after handshake)
def new_client(client, server: WebsocketServer):
    logging.debug(f"New ESP client connected and was given id {client['id']:d}")
    if client['address'][0] in previous_connections:
        client_server.send_console_message(
            f'Wi-Fi module with previous name {previous_connections[client["address"][0]]} reconnected... waiting for begin statement. (Not beginning? See Vision System Troubleshooting at enes100.umd.edu)')
    else:
        client_server.send_console_message(f'New Wi-Fi module connected... waiting for begin statement. (Not beginning? See Vision System Troubleshooting at enes100.umd.edu)')


# Called for every client disconnecting
def client_left(client, _):
    if client is None:
        return
    client_server.send_console_message(f'Team {get_team_name(client)} disconnected...')
    if 'address' not in client or len(client['address']) == 0:
        return
    if client['address'][0] not in ignorable_disconnects:
        client_server.send_console_message(f'Unknown ESP disconnected... mysterious')
    ignorable_disconnects.discard(client['address'][0])

# Called when a Wi-Fi client sends a message
def message_received(client, server: WebsocketServer, message):
    if client is None:
        logging.debug(f'Unknown client sent a message - {message}')
        return

    import main
    if main.log_requests['esp']:
        logging.debug(f'Team: "{client.get("teamName") if client.get("teamName") else "No Team Name"}" sent message {message}')
    try:
        message = json.loads(message)
        if message is None:
            client_server.send_console_message(
                f'Team {get_team_name(client)} sent an invalid message. Try pressing the reset button on your arduino. (Empty Message)')
            return
    except json.JSONDecodeError:
        logging.debug(f'Invalid JSON: {message}')
        client_server.send_console_message(
            f'Team {get_team_name(client)} sent an invalid message. Try pressing the reset button on your arduino. (JSON Parse Error)')
        return

    if message['op'] == 'begin':
        # Check to make sure the team name is unique
        if message['teamName'] in [get_team_name(c) for c in ws_server.clients if c != client]:
            client_server.send_console_message(
                f'Team name {message["teamName"]} is already in use. Please choose a different name.')
            return
        client['teamName'] = message['teamName']
        previous_connections[client['address'][0]] = client['teamName']
        client['teamType'] = team_types[message['teamType']]
        # Optional aruco argument. If not provided, it will be None.
        client['aruco'] = {'num': message.get('aruco'), 'visible': False, 'x': None, 'y': None, 'theta': None}

        ignorable_disconnects.discard(client['address'][0])  # This client is now valid.
        hardware = message.get('hardware', 'WiFi Module')
        client_server.send_console_message(f'Team {get_team_name(client)} got begin statement ({hardware})')
        if data.dr_op.aruco_markers.get(client['aruco']['num']) is None:
            shown_markers = [str(marker) for marker in list(data.dr_op.aruco_markers.keys()) if marker > 3]
            msg = f'The visible aruco markers are {",".join(shown_markers)}.' if shown_markers else 'No aruco markers are visible.'
            client_server.send_console_message(f'Warning: Team {get_team_name(client)} registered with ArUco num {client["aruco"]["num"]} but it is not visible! ' + msg)
    if message['op'] == 'print':
        # if random.random() < 0.00005 and message['message'].endswith('\n'):
        #     message['message'] += 'LTF > UTF :)\n'
        if 'teamName' in client:
            client_server.send_print_message(client['teamName'], message['message'])
        else:
            # logging.debug('An unknown team said' + message['message'])
            pass
    if message['op'] == 'mission':
        if 'teamName' not in client:
            if once():
                client_server.send_console_message(
                    f'Client {get_team_name(client)} sent mission message before begin statement. Try pressing the reset button on your arduino.')
            return
        # logging.debug(f'Mission submission from team {client["teamName"]}.')
        client_server.send_print_message(client['teamName'],
                                         get_mission_message(client['teamType'], message['type'], message['message']))
    if message['op'] == 'prediction_request':
        if 'teamName' not in client:
            client_server.send_console_message(
                f'Client {get_team_name(client)} called prediction_request before begin statement. Try pressing the reset button on your arduino.')
        if not message['modelIndex']:
            client_server.send_console_message(
                f'Client {get_team_name(client)} called prediction_request without providing a model index')
        if not jetson_server.request_prediction(client['teamName'], client['address'], message['modelIndex']):
            client_server.send_console_message(f'Team {get_team_name(client)} requested a prediction but no jetson could be found.')
        else:
          client_server.send_console_message(f'ML prediction from team {get_team_name(client)} requested. Waiting for response.')

def send_locations():
    # print(dr_op.aruco_markers[402])
    for client in ws_server.clients:
        if client and client.get('aruco') is not None and client['aruco']['num'] is not None:
            if data.dr_op.aruco_markers.get(client['aruco']['num']):
                aruco = data.dr_op.aruco_markers[client['aruco']['num']]
                client['aruco']['visible'] = True
                client['aruco']['x'] = round(float(aruco.x), 2)
                client['aruco']['y'] = round(float(aruco.y), 2)
                client['aruco']['theta'] = round(float(aruco.theta), 2)
            else:
                client['aruco']['visible'] = False
                client['aruco'].update({'visible': False, 'x': -1, 'y': -1, 'theta': -1})
            ws_server.send_message(client, json.dumps({'op': 'aruco', 'aruco': client['aruco']}))


# esp_server.send_prediction(client['teamName'], message['prediction'])
def send_prediction(team_name, prediction):
    if prediction is None:
        return
    for client in ws_server.clients:
        if client and client.get('teamName') == team_name:
            ws_server.send_message(client, json.dumps({'op': 'prediction', 'prediction': prediction}))
            return
    client_server.send_console_message(
        f'Could not find Wifi Module for team {team_name} to send prediction results to.')


# noinspection PyTypeChecker
def start_server():
    global ws_server
    ws_server = None
    try:
        if local:
            if 'host' in sys.argv:
                ws_server = WebsocketServer(port=7755, host=sys.argv[sys.argv.index('host') + 1])
            else:
                ws_server = WebsocketServer(port=7755)
        else:
            ws_server = WebsocketServer(host='192.168.1.2', port=7755)
    except OSError as e:
        if e.errno == 98:
            logging.error('Program is already running on this computer. Please close other instance.')
            exit(1)

    try:
        if ws_server is None:
            logging.error('esp_server:233 -> ws_server is None. Did you make sure to set the network up correctly? (Assign static IP on wired connection) See readme.md')
            return
    except NameError:
        logging.error(
            'client_server -> ws_server is not defined. Did you make sure to set the network up correctly? (Assign static IP on wired connection) See readme.md')
        return
    ws_server.set_fn_new_client(new_client)
    ws_server.set_fn_client_left(client_left)
    ws_server.set_fn_message_received(message_received)
    logging.debug(f'Starting client ws_server on port {ws_server.port:d}')
    threading.Thread(target=ws_server.run_forever, name='ESP WS Server', daemon=True).start()

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

    threading.Thread(target=check_connection, daemon=True, name='ESP Check Connection').start()

