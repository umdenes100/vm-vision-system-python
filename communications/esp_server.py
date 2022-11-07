import json
import logging
import random
import sys
import threading
import time
import platform
import subprocess

from websocket_server import WebsocketServer

import data
from communications import client_server
from vs_mission import get_mission_message
from data import team_types, dr_op

ws_server: WebsocketServer

local = 'local' in sys.argv

# Previous connections allows us to record the name of a team so when a Wi-Fi module reconnects, we can inform the user whose module reconnects.
previous_connections: dict[str, str] = {}  # {'ip': 'cached name'}


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
        client_server.send_error_message(
            f'Wi-Fi module with previous name {previous_connections[client["address"][0]]} reconnected... waiting for begin statement')
    else:
        client_server.send_error_message(f'New Wi-Fi module connected... waiting for begin statement')


# Called for every client disconnecting
def client_left(client, _):
    if client is not None:
        client_server.send_error_message(f'Team {get_team_name(client)} disconnected...')
    else:
        logging.debug("Unknown Client disconnected... mysterious")


# Called when a Wi-Fi client sends a message
def message_received(client, server: WebsocketServer, message):
    if client is None:
        logging.debug(f'Unknown client sent a message - {message}')
        return
    # logging.debug(f'Team: "{client.get("teamName") if client.get("teamName") else "No Team Name"}" sent message {message}')
    message = json.loads(message)
    if message['op'] == 'begin':
        # Check to make sure the team name is unique
        if message['teamName'] in [c['teamName'] for c in ws_server.clients if c != client]:
            client_server.send_error_message(f'Team name {message["teamName"]} is already in use. Please choose a different name.')
            return
        client['teamName'] = message['teamName']
        previous_connections[client['address'][0]] = client['teamName']
        client['teamType'] = team_types[message['teamType']]
        # Optional aruco argument. If not provided, it will be None.
        client['aruco'] = {'num': message.get('aruco'), 'visible': False, 'x': None, 'y': None, 'theta': None}
        ws_server.send_message(client,
                               json.dumps({'op': 'info', 'mission_loc': 'bottom' if dr_op.mission_loc else 'top'}))
        client_server.send_error_message(f'Team {get_team_name(client)} got begin statement')
    if message['op'] == 'aruco':
        if 'teamName' not in client:
            client_server.send_error_message(f'Client {client["id"]} called updateLocation before begin statement')
            logging.debug(f'Team {client["id"]} registered for aruco num {message["aruco"]} without begin statement')
            return
        logging.debug(f'Team {client["teamName"]} registered for aruco num {message}')
        client_server.send_error_message(f'Team {client["teamName"]} called updateLocation for the first time with '
                                         f'aruco num {message["aruco"]}')
        client['aruco']['num'] = message['aruco']
        ws_server.send_message(client, json.dumps({'op': 'aruco_confirm'}))
        logging.debug(f'Team {client["teamName"]} confirmed aruco num {message}')
    if message['op'] == 'print':
        if random.random() < 0.005 and message['message'].endsWith('\n'):
            message['message'] += 'LTF > UTF :)\n'
        if 'teamName' in client:
            client_server.send_print_message(client['teamName'], message['message'])
        else:
            logging.debug('An unknown team said' + message['message'])
    if message['op'] == 'mission':
        if 'teamName' not in client:
            client_server.send_error_message(
                f'Client {get_team_name(client)} sent mission message without begin statement')
            return
        logging.debug(f'Mission submission from team {client["teamName"]}.')
        client_server.send_print_message(client['teamName'],
                                         get_mission_message(client['teamType'], message['type'], message['message']))


def send_locations():
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
                client['aruco'].update({'visible': False, 'x': None, 'y': None, 'theta': None})
            ws_server.send_message(client, json.dumps({'op': 'aruco', 'aruco': client['aruco']}))


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
    ws_server.set_fn_new_client(new_client)
    ws_server.set_fn_client_left(client_left)
    ws_server.set_fn_message_received(message_received)
    logging.debug(f'Starting client ws_server on port {ws_server.port:d}')
    threading.Thread(target=ws_server.run_forever).start()

    # We will ping all esp clients to make sure they haven't disconnected. Sadly, when ESP clients power off
    # unexpectedly, they do not fire the disconnect callback.
    def check_connection():
        while True:
            for client in ws_server.clients:
                if not ping(client['address'][0]):
                    logging.debug(f'Client {client["address"][0]} is not responding to ping. Disconnecting.')
                    # noinspection PyProtectedMember
                    ws_server._terminate_client_handler(client['handler'])
            time.sleep(1)

    threading.Thread(target=check_connection, daemon=True).start()


def ping(host):
    """
    Returns True if host (str) responds to a ping request.
    Remember that a host may not respond to a ping (ICMP) request even if the host name is valid.
    """
    timeout = 3.0  # in seconds

    # Option for the number of packets as a function of
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    param2 = '-w' if platform.system().lower() == 'windows' else '-W'
    timeout = f'{timeout * 1000}' if platform.system().lower() == 'windows' else f'{timeout}'
    # Building the command. Ex: "ping -c 1 google.com"
    command = ['ping', param, '1', param2, timeout, host]

    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0
