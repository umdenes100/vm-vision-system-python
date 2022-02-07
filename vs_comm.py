import socket
import threading
from _thread import *
import json
import time
import cv2
import websocket
from subprocess import Popen, PIPE
from vs_mission import *
from vs_opencv import aruco_markers
import asyncio
import websockets
from websocket_server import WebsocketServer
import hashlib
import base64
import struct

image_frame_list = []

FIN    = 0x80
OPCODE = 0x0f
MASKED = 0x80
PAYLOAD_LEN = 0x7f
PAYLOAD_LEN_EXT16 = 0x7e
PAYLOAD_LEN_EXT64 = 0x7f

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT         = 0x1
OPCODE_BINARY       = 0x2
OPCODE_CLOSE_CONN   = 0x8
OPCODE_PING         = 0x9
OPCODE_PONG         = 0xA

CLOSE_STATUS_NORMAL = 1000

class Connections:
    def __init__(self):
        self.team_connections = {}
        self.message_connections = []
        self.image_connections = []
        self.udp_connections = {}
        self.video = cv2.VideoCapture(0)

    def get_team_conns(self):
        return self.team_connections

    def get_msg_conns(self):
        return self.message_connections

    def get_img_conns(self):
        return self.image_connections

    def get_udp_conns(self):
        return self.udp_connections

    def get_cam(self):
        return self.video

    def set_team_conns(self, tcs):
        self.team_connections = tcs

    def set_msg_conns(self, mcs):
        self.message_connections = mcs
    
    def set_img_conns(self, ics):
        self.image_connections = ics

    def set_udp_conns(self, ucs):
        self.udp_connections = ucs

    def set_cam(self, num):
        self.video.release()
        p = Popen(["v4l2-ctl", f"--device=/dev/video{num}", "--all"], stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, err = p.communicate()
        if "brightness" in output.decode(): 
            self.video = cv2.VideoCapture(num)
            self.video.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')) # depends on fourcc available camera
            self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


def udpthread(conn, connections):
    print("udp thread started")
    while 1:
        udp_connections = connections.get_udp_conns()
        data, addr = conn.recvfrom(1024)
        ip, port = addr
        ip = str(ip)

        # add ip to udp connections for future use
        data_to_send = b''
        if not (ip in udp_connections.keys()):
            #udp_connections[ip] = {'ip': ip} # may not need this extra info in there since the ip IS the key
            udp_connections[ip] = {}

        second = data[1]
        
        # PING
        if second == 0:
            data_to_send = b'\x01' # ping back hehe
       
        # BEGIN (START)
        elif second == 2:
            mission = data[2]
            teamname = data[3:].decode()
            udp_connections[ip]['NAME'] = teamname

            if mission == 0:
                udp_connections[ip]['MISSION'] = "CRASH_SITE"
            elif mission == 1:
                udp_connections[ip]['MISSION'] = "DATA"
            elif mission == 2:
                udp_connections[ip]['MISSION'] = "MATERIAL"
            elif mission == 3:
                udp_connections[ip]['MISSION'] = "FIRE"
            elif mission == 4:
                udp_connections[ip]['MISSION'] = "WATER"
            else:
                udp_connections[ip]['MISSION'] = "unknown"

            print(f"\nTeam Name: {teamname}\nMission: {mission}\n")
            
            send_message(udp_connections, 'PORT_LIST', connections) # sends new port list to each connection
            print(f"UDP_CONNECTIONS = {udp_connections}")
            send_message(str(int(time.time())), 'START', connections) # send start command to msg server

            # TODO - return the mission destination - OpenCV
            
            data_to_send = b'\x03'
        
        # LOCATION REQUEST
        elif second == 4:
            markerId = data[2] | (data[3] << 8)
            
            # TODO - get marker location - OpenCV
            
            found = False
            if found:
                data_to_send = b'\x05'
            else:
                data_to_send = b'\x09'
            
            # TODO - append location data to data_to_send - OpenCV
            
            print(f'markerId = {markerId}')
        
        # MISSION
        elif second == 6:
            message = data[3:]
            curr = data[2]

            # send message to message server
            send_message(get_mission_message(curr, udp_connections[ip]['MISSION'], message), 'MISSION', connections)
            data_to_send = b'\x07'
        
        # DEBUG
        elif second == 8:
            msg = data[2:].decode()
            send_message(msg, 'DEBUG', connections) # send debug message to msg server
            print(f"Debug message = {msg}")

        conn.sendto(data_to_send, addr)
        connections.set_udp_conns(udp_connections)
        #print(f'ip = {ip} --- data = {data} --- sec = {second}')

def send_message(msg, m_type, connections):
    json_stuff = json.dumps({'TYPE': m_type, 'CONTENT': msg})
    send_text(json_stuff, connections)

def send_text(data, connections, opcode=OPCODE_TEXT):
    header  = bytearray()
    payload = data.encode()
    payload_length = len(payload)

    # Normal payload
    if payload_length <= 125:
        header.append(FIN | opcode)
        header.append(payload_length)

    # Extended payload
    elif payload_length >= 126 and payload_length <= 65535:
        header.append(FIN | opcode)
        header.append(PAYLOAD_LEN_EXT16)
        header.extend(struct.pack(">H", payload_length))

    # Huge extended payload
    elif payload_length < 18446744073709551616:
        header.append(FIN | opcode)
        header.append(PAYLOAD_LEN_EXT64)
        header.extend(struct.pack(">Q", payload_length))

    else:
        raise Exception("Message is too big. Consider breaking it into chunks.")
        return

    for d in connections.get_msg_conns():
        conn = d['conn']
        conn.sendall(header + payload)


# This is a complicated receive function for websocket
def read_next_message(message_in):
    b1, b2 = message_in[0], message_in[1]

    fin    = b1 & FIN
    opcode = b1 & OPCODE
    masked = b2 & MASKED
    payload_length = b2 & PAYLOAD_LEN

    if opcode == OPCODE_CLOSE_CONN:
        print("Client asked to close connection.")
        return "CLOSE"
    if not masked:
        print("Client must always be masked.")
        return "CLOSE"
    if opcode == OPCODE_CONTINUATION:
        print("Continuation frames are not supported.")
        return "CONTINUE"
    elif opcode == OPCODE_BINARY:
        print("Binary frames are not supported.")
        return "CONTINUE"
    elif opcode == OPCODE_TEXT:
        print("opcode == OPCODE_TEXT")
    elif opcode == OPCODE_PING:
        print("PING_RECEIVED")
        return "PING"
    elif opcode == OPCODE_PONG:
        return "PONG"
    else:
        print("Unknown opcode %#x." % opcode)
        #self.keep_alive = 0
        return "CLOSE"

    if payload_length == 126:
        payload_length = struct.unpack(">H", message_in[2:4])[0]
        masks = message_in[4:8]
        start = 8
    elif payload_length == 127:
        payload_length = struct.unpack(">Q", message_in[2:10])[0]
        masks = message_in[10:14]
        start = 14
    else:
        masks = message_in[2:6]
        start = 6

    message_bytes = bytearray()
    for message_byte in message_in[start:start+payload_length]:
        message_byte ^= masks[len(message_bytes) % 4]
        message_bytes.append(message_byte)
    
    return message_bytes.decode()

# The front-end will send messages back depending on which clients are choosing to
# view which UDP connections (aka which team from the frop-down menu)!
def rec_msg(conn, connections):
    # gather received messages and process
    while 1:
        data = conn.recv(1024)
        if len(data) == 0:
            continue

        print(f"Data received as {data}")
        team_connections = connections.get_team_conns()
        if b"websocket" in data:
            data = data.decode()
            print(data)
            key = data.split('Sec-WebSocket-Key: ')[1].split('\r\n')[0]
            guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            print(f"key = {key+guid}")
            accepted = base64.b64encode(hashlib.sha1((key+guid).encode()).digest()).strip().decode('ASCII')
            print(f"accepted = {accepted}")
            to_send = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            to_send += f"Sec-WebSocket-Accept: {accepted}\r\n\r\n" 
            conn.sendall(to_send.encode())
            print("sent")
            # TODO - send udp conns?
            send_text(json.dumps({"TYPE": "PORT_LIST", "CONTENT": connections.get_udp_conns()}), connections)
        else:
            msg = read_next_message(data)

            if msg == "PING":
                send_text(data, connections, OPCODE_PONG)
                continue
            elif msg == "PONG":
                print("PONG RECEIVED")
                continue
            elif msg == "CLOSE":
                # TODO - delete conn in database
                conn.close()
                break
            elif msg == "CONTINUE":
                continue

            print(f"data received = {msg}")
            data = json.loads(msg)

            if data['TYPE'] == "OPEN":
                if len(team_connections[data['PORT']]) > 0:
                    team_connections[data['PORT']].append(conn)
                else:
                    team_connections[data['PORT']] = [conn]
            
            elif data['TYPE'] == "SWITCH":
                new_port = data['NEW_PORT']
                team_connections[data['PORT']].remove(conn)
                if len(team_connections[new_port]) > 0:
                    team_connections[new_port].append(conn)
                else:
                    team_connections[new_port] = [conn]
            
            elif data['TYPE'] == "HARD_CLOSE":
                team_connections[data['PORT']].remove(conn)

            elif data['TYPE'] == "SOFT_CLOSE":
                if len(data['PORT']) > 0:
                    team_connections[data['PORT']].remove(conn)

        connections.set_team_conns(team_connections)
    
    #print("message stuff here?")
    conn.close()


# send new image frame to each of the connections
def send_frame(frame, connections):
    #print("sending image frame")
    image_connections = connections.get_img_conns()

    # ONE WAY image service
    # on new frame, send JPEG byte array to each connection

    data = b'--newframe\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
    #print(f'frame = {frame}')
    data += frame

    for i in range(len(image_connections)):
        # send frame
        conn = image_connections[i]['conn']
        try:
            conn.sendall(data)
        except:
            print(f"image failed to send to {image_connections[i]['addr']}")
            conn.close()
            image_connections = image_connections[0:i] + image_connections[i+1:] 
   
    #print("finished")
    connections.set_img_conns(image_connections)

def accept_image_conns(image_s, connections):
    while True:
        img_conn, addr = image_s.accept()
        
        ics = connections.get_img_conns()
        ics.append({'conn': img_conn, 'addr': addr})
        connections.set_img_conns(ics)

        img_conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=newframe\r\n\r\n')
        print(f'image_conns = {ics}\n')

#def new_client(client, server):
#    print(f"New client connected: id = {client['id']}")
#
#def client_left(client, server):
#    print(f"Client {client['id']} has disconnected")
#
#def message_received(client, server, message):
#    print(f"Client {client['id']} said: {message}")
#

def start_communication(connections):
    udp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_s.bind(("", 7755))
    start_new_thread(udpthread, (udp_s, connections, ))

    message_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    message_s.bind(("", 9000))
    message_s.listen()

    image_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    image_s.bind(("", 8080))
    image_s.listen() # start new thread for accepting new image servers
    start_new_thread(accept_image_conns, (image_s, connections, ))

    #server = WebsocketServer(port = 9000)
    #server.set_fn_new_client(new_client)
    #server.set_fn_client_left(client_left)
    #server.set_fn_message_received(message_received)
    #server.run_forever()

    
    # continue this main thread with accepting message servers
    while True:
        msg_conn, addr = message_s.accept()
        ip, port = addr

        message_connections = connections.get_msg_conns()
        #ws = websocket.WebSocket()
        #ws = websocket.create_connection(f"ws://{ip}:{port}/")
        message_connections.append({'conn': msg_conn, 'addr': addr})
        #message_connections.append({'conn': msg_conn, 'addr': addr})
        connections.set_msg_conns(message_connections)
        print(f'message_conns = {message_connections}\n')

        # send initial json stuff and initial message to website
        #msg_conn.sendall(json.dumps({"TYPE": "PORT_LIST", "CONTENT": connections.get_udp_conns()}).encode())
        #start_new_thread(rec_msg, (msg_conn, connections, ))
        start_new_thread(rec_msg, (msg_conn, connections, ))

    

