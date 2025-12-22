import json
import logging
import sys
import threading
import time
from typing import Optional, Dict, Set, Any, List

from websocket_server import WebsocketServer

from components import data
from components.communications import client_server
from components.communications.ping import ping
from components.machinelearning import ml
from components.vs_mission import get_mission_message

# Global server instance (used by send_prediction)
ws_server: Optional[WebsocketServer] = None

# CLI flags / options
local = 'local' in sys.argv

# Previous connections allows us to record the name of a team so when a Wi-Fi module reconnects,
# we can inform the user whose module reconnects.
previous_connections: Dict[str, str] = {}  # {'ip': 'cached name'}

# List of IPs that we have forcibly disconnected. We don't want to send an error message for these.
ignorable_disconnects: Set[str] = set()


def _get_team_types() -> List[str]:
    """
    Resolve the mission/team-type strings without relying on components.data.team_types.

    The ESP "begin" message provides teamType as an integer index. Historically this mapped to:
      0: Sand
      1: Sample
      2: Data
      3: Water

    We prefer deriving from data.teams (which already contains mission strings), and fall back
    to the canonical list if needed.
    """
    try:
        missions = [t.get('mission') for t in getattr(data, 'teams', []) if isinstance(t, dict)]
        missions = [m for m in missions if isinstance(m, str) and m.strip()]
        # If missions look sane and include at least 4 entries, use them (preserves repo's ordering).
        if len(missions) >= 4:
            return missions
    except Exception:
        pass

    return ["Sand", "Sample", "Data", "Water"]


def once() -> bool:
    """
    Returns True only once per callsite (filename + lineno). Used to avoid spamming the console.
    """
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


def get_team_name(client: Dict[str, Any]) -> str:
    """
    Helper message to get the team's name to the best of our knowledge.
    """
    if client is None:
        return "Unknown Client"
    if 'teamName' in client:
        return client['teamName']
    ip = (client.get('address') or [''])[0]
    if ip in previous_connections:
        return '(Cached Name)' + previous_connections[ip]
    return f'No Team Name (IP: {ip})'


def _should_log_esp_requests() -> bool:
    """
    Older code referenced main.log_requests['esp']. Newer main.py may not have it.
    This keeps behavior compatible without hard-depending on it.
    """
    try:
        import main  # type: ignore
        lr = getattr(main, 'log_requests', None)
        if isinstance(lr, dict):
            return bool(lr.get('esp', False))
    except Exception:
        pass
    return False


# Called for every client connecting (after handshake)
def new_client(client: Dict[str, Any], _server: WebsocketServer) -> None:
    print("Connected")
    logging.debug(f"New ESP client connected and was given id {client.get('id')!s}")

    ip = (client.get('address') or [''])[0]
    if ip in previous_connections:
        client_server.send_console_message(
            f'Wi-Fi module with previous name {previous_connections[ip]} reconnected... waiting for begin statement. '
            f'(Not beginning? See Vision System Troubleshooting at enes100.umd.edu)'
        )
    else:
        client_server.send_console_message(
            'New Wi-Fi module connected... waiting for begin statement. '
            '(Not beginning? See Vision System Troubleshooting at enes100.umd.edu)'
        )


# Called for every client disconnecting
def client_left(client: Optional[Dict[str, Any]], _server: WebsocketServer) -> None:
    if client is None:
        return

    client_server.send_console_message(f'Team {get_team_name(client)} disconnected...')
    print("Disconnected")

    addr = client.get('address')
    if not addr or len(addr) == 0:
        return

    ip = addr[0]
    if ip not in ignorable_disconnects:
        client_server.send_console_message('Unknown ESP disconnected... mysterious')
    ignorable_disconnects.discard(ip)


# Called when a Wi-Fi client sends a message
def message_received(client: Optional[Dict[str, Any]], _server: WebsocketServer, message: str) -> None:
    global ws_server

    if client is None:
        print(f'Unknown client sent a message - {message}')
        return

    if _should_log_esp_requests():
        logging.debug(
            f'Team: "{client.get("teamName") if client.get("teamName") else "No Team Name"}" sent message {message}'
        )

    try:
        msg = json.loads(message)
        if msg is None:
            client_server.send_console_message(
                f'Team {get_team_name(client)} sent an invalid message. '
                f'Try pressing the reset button on your arduino. (Empty Message)'
            )
            return
    except json.JSONDecodeError:
        logging.debug(f'Invalid JSON: {message}')
        client_server.send_console_message(
            f'Team {get_team_name(client)} sent an invalid message. '
            f'Try pressing the reset button on your arduino. (JSON Parse Error)'
        )
        return
    except Exception as e:
        logging.debug(f'Error parsing message: {e}')
        return

    op = msg.get('op')
    if op is None:
        return

    # ---- BEGIN ----
    if op == 'begin':
        team_name = msg.get('teamName')
        team_type_idx = msg.get('teamType')

        if not isinstance(team_name, str) or not team_name.strip():
            client_server.send_console_message(
                f'Team {get_team_name(client)} sent begin without a valid teamName.'
            )
            return

        # Check to make sure the team name is unique
        if ws_server and team_name in [get_team_name(c) for c in ws_server.clients if c != client]:
            client_server.send_console_message(
                f'Team name {team_name} is already in use. Please choose a different name.'
            )
            return

        client['teamName'] = team_name
        ip = (client.get('address') or [''])[0]
        previous_connections[ip] = team_name

        team_types = _get_team_types()
        try:
            # teamType is expected to be an index
            if isinstance(team_type_idx, int) and 0 <= team_type_idx < len(team_types):
                client['teamType'] = team_types[team_type_idx]
            else:
                # Accept legacy string teamType (if some client sends it)
                if isinstance(team_type_idx, str) and team_type_idx.strip():
                    client['teamType'] = team_type_idx.strip()
                else:
                    client['teamType'] = team_types[0]
        except Exception:
            client['teamType'] = team_types[0]

        # Optional aruco argument. If not provided, it will be None.
        client['aruco'] = {
            'num': msg.get('aruco'),
            'visible': False,
            'x': None,
            'y': None,
            'theta': None,
        }

        ignorable_disconnects.discard(ip)  # This client is now valid.

        hardware = msg.get('hardware', 'WiFi Module')
        client_server.send_console_message(f'Team {get_team_name(client)} got begin statement ({hardware})')

        # Append to file to keep track of team joins
        try:
            with open('matt_paul_team_join_history.csv', 'a') as f:
                f.write(f'{time.time()},{client["teamName"]},{client["teamType"]}\n')
        except Exception:
            pass

        # Warn if their marker isn't currently visible
        try:
            aruco_num = client.get('aruco', {}).get('num')
            if aruco_num is not None and data.dr_op.aruco_markers.get(aruco_num) is None:
                shown_markers = [str(marker) for marker in list(data.dr_op.aruco_markers.keys()) if marker > 3]
                msg2 = (
                    f'The visible aruco markers are {",".join(shown_markers)}.'
                    if shown_markers else 'No aruco markers are visible.'
                )
                client_server.send_console_message(
                    f'Warning: Team {get_team_name(client)} registered with ArUco num {aruco_num} but it is not visible! '
                    + msg2
                )
        except Exception:
            pass

        return

    # ---- PRINT ----
    if op == 'print':
        if 'teamName' in client:
            client_server.send_print_message(client['teamName'], msg.get('message', ''))
        return

    # ---- MISSION ----
    if op == 'mission':
        if 'teamName' not in client:
            if once():
                client_server.send_console_message(
                    f'Client {get_team_name(client)} sent mission message before begin statement. '
                    f'Try pressing the reset button on your arduino.'
                )
            return

        mission_type = msg.get('type')
        mission_message = msg.get('message')
        client_server.send_print_message(
            client['teamName'],
            get_mission_message(client.get('teamType'), mission_type, mission_message)
        )
        return

    # ---- PREDICTION REQUEST ----
    if op == 'prediction_request':
        if 'teamName' not in client:
            client_server.send_console_message(
                f'Client {get_team_name(client)} called prediction_request before begin statement. '
                f'Try pressing the reset button on your arduino.'
            )
            return

        model_index = msg.get('modelIndex')
        if not model_index:
            client_server.send_console_message(
                f'Client {get_team_name(client)} called prediction_request without providing a model index'
            )
            return

        client_server.send_console_message(
            f'Client {get_team_name(client)} called prediction_request. Processing using VS Computer (CPU)'
        )

        task = {
            'ip': (client.get('address') or [''])[0],
            'team_name': client.get('teamName'),
            'model_index': model_index
        }
        if msg.get('frame'):
            task['frame'] = msg.get('frame')

        try:
            ml.ml_processor.enqueue(task)
        except Exception as e:
            client_server.send_console_message(f'Prediction request failed to enqueue: {e}')
        return


def send_locations(server: Optional[WebsocketServer]) -> None:
    """
    Periodically send ArUco pose updates to connected ESP clients.
    """
    if server is None:
        print("[ERROR] send_locations called with server=None, aborting")
        return

    # Keep original behavior: tolerate short periods of invisibility before declaring not-visible.
    trybacks = 0

    while True:
        for client in list(server.clients):
            if not client:
                continue

            aruco = client.get('aruco')
            if not isinstance(aruco, dict):
                continue

            aruco_num = aruco.get('num')
            if aruco_num is None:
                continue

            marker = data.dr_op.aruco_markers.get(aruco_num)
            if marker:
                aruco.update({
                    'visible': True,
                    'x': round(float(marker.x), 2),
                    'y': round(float(marker.y), 2),
                    'theta': round(float(marker.theta), 2),
                })
                trybacks = 0
            elif trybacks < 5:
                trybacks += 1
            else:
                aruco.update({
                    'visible': False,
                    'x': -1,
                    'y': -1,
                    'theta': -1,
                })
                trybacks = 0

            try:
                server.send_message(client, json.dumps({'op': 'aruco', 'aruco': aruco}))
            except Exception:
                # Client may have disconnected mid-loop
                pass

        # avoid a tight busy loop
        time.sleep(0.05)


def send_prediction(team_name: str, prediction: Any) -> None:
    """
    Send prediction result to a specific team over the ESP websocket channel.
    """
    global ws_server

    if prediction is None:
        return
    if ws_server is None:
        client_server.send_console_message('ESP server not running; cannot send prediction.')
        return

    for client in list(ws_server.clients):
        if client and client.get('teamName') == team_name:
            try:
                ws_server.send_message(client, json.dumps({'op': 'prediction', 'prediction': prediction}))
            except Exception:
                pass
            return

    client_server.send_console_message(
        f'Could not find Wifi Module for team {team_name} to send prediction results to.'
    )


# noinspection PyTypeChecker
def start_server() -> Optional[WebsocketServer]:
    """
    Start the ESP websocket server and connection monitor thread.
    """
    global ws_server

    ws_server = None
    try:
        if local:
            if 'host' in sys.argv:
                ws_server = WebsocketServer(port=7755, host=sys.argv[sys.argv.index('host') + 1])
            else:
                ws_server = WebsocketServer(port=7755)
        else:
            ws_server = WebsocketServer(host='0.0.0.0', port=7755)
    except OSError as e:
        if getattr(e, 'errno', None) == 98:
            logging.error('[ESP Server] >>> Program is already running on this computer. Please close other instance.')
            sys.exit(1)
        raise

    if ws_server is None:
        logging.error(
            'esp_server -> ws_server is None. Did you make sure to set the network up correctly? '
            '(Assign static IP on wired connection) See readme.md'
        )
        return None

    ws_server.set_fn_new_client(new_client)
    ws_server.set_fn_client_left(client_left)
    ws_server.set_fn_message_received(message_received)

    threading.Thread(target=ws_server.run_forever, name='ESP WS Server', daemon=True).start()

    # Ping all esp clients to make sure they haven't disappeared without a disconnect callback.
    def check_connection():
        while True:
            try:
                for client in list(ws_server.clients):
                    ip = (client.get('address') or [''])[0]
                    if ip and not ping(ip):
                        logging.debug(f'Client {ip} is not responding to ping. Disconnecting.')
                        ignorable_disconnects.add(ip)
                        # noinspection PyProtectedMember
                        ws_server._terminate_client_handler(client['handler'])
            except Exception:
                pass
            time.sleep(1)

    threading.Thread(target=check_connection, daemon=True, name='ESP Check Connection').start()
    return ws_server
