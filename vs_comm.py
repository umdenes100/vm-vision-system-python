import socket
import threading
from _thread import *
import json
import time
import cv2
import hashlib
import base64
from subprocess import Popen, PIPE
from vs_mission import *
from vs_opencv import aruco_markers
from vs_ws import *

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
            
            send_message(udp_connections, 'PORT_LIST', connections, "ALL") # sends new port list to each connection
            print(f"UDP_CONNECTIONS = {udp_connections}")
            send_message(str(int(time.time())), 'START', connections, ip) # send start command to msg server

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
            send_message(get_mission_message(curr, udp_connections[ip]['MISSION'], message), 'MISSION', connections, ip)
            data_to_send = b'\x07'
        
        # DEBUG
        elif second == 8:
            msg = data[2:].decode()
            send_message(msg, 'DEBUG', connections, ip) # send debug message to msg server
            print(f"Debug message = {msg}")

        conn.sendto(data_to_send, addr)
        connections.set_udp_conns(udp_connections)
        #print(f'ip = {ip} --- data = {data} --- sec = {second}')

# format for calling send_text()
def send_message(msg, m_type, connections, ip):
    json_stuff = json.dumps({'TYPE': m_type, 'CONTENT': msg})
    #send_text(json_stuff, connections)

    # TODO - only send to connections that have that UDP port open (aka. the team name selected)
    data = json_stuff
    for d in connections.get_msg_conns():
        if ip == "ALL" or d['open'] == ip:
            send_text(data, d['conn'])

        
# The front-end will send messages back depending on which clients are choosing to
# view which UDP connections (aka which team from the frop-down menu)!
def rec_msg(conn, connections):
    # gather received messages and process
    while 1:
        data = conn.recv(1024)
        if len(data) == 0:
            continue

        #print(f"Data received as {data}")
        team_connections = connections.get_team_conns()
        msg_conns = connections.get_msg_conns()
        
        # get index in msg_conns array for later use
        for i in range(len(msg_conns)):
            if msg_conns[i]['conn'] == conn:
                break

        if b"websocket" in data:
            data = data.decode()
            #print(data)
            key = data.split('Sec-WebSocket-Key: ')[1].split('\r\n')[0]
            guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            #print(f"key = {key+guid}")
            accepted = base64.b64encode(hashlib.sha1((key+guid).encode()).digest()).strip().decode('ASCII')
            #print(f"accepted = {accepted}")
            to_send = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            to_send += f"Sec-WebSocket-Accept: {accepted}\r\n\r\n" 
            conn.sendall(to_send.encode())
            #print("sent")
            #send_text(json.dumps({"TYPE": "PORT_LIST", "CONTENT": connections.get_udp_conns()}), connections)
            send_message(connections.get_udp_conns(), 'PORT_LIST', connections, "ALL") # sends new port list to each connection
            print("handshake complete")
        else:
            msg = read_next_message(data)

            if msg == "PING":
                send_text(data, connections, OPCODE_PONG) 
                continue
            elif msg == "PONG":
                print("PONG RECEIVED")
                continue
            elif msg == "CLOSE":
                #team_connections[data['PORT']].remove(conn)
                for mc in msg_conns:
                    if mc['conn'] == conn:
                        msg_conns.remove(mc)
                        break
                conn.close()
                break
            elif msg == "CONTINUE":
                continue

            print(f"data received = {msg}")
            data = json.loads(msg)

            if data['TYPE'] == "OPEN":
                #if len(team_connections[data['PORT']]) > 0:
                #    team_connections[data['PORT']].append(conn)
                #else:
                #    team_connections[data['PORT']] = [conn]
                msg_conns[i]['open'] = data['PORT']
            
            elif data['TYPE'] == "SWITCH":
                #new_port = data['NEW_PORT']
                #team_connections[data['PORT']].remove(conn)
                #if len(team_connections[new_port]) > 0:
                #    team_connections[new_port].append(conn)
                #else:
                #    team_connections[new_port] = [conn]
                msg_conns[i]['open'] = data['PORT']
            
            elif data['TYPE'] == "HARD_CLOSE": # TODO - what to do for hard close?
                #team_connections[data['PORT']].remove(conn)
                msg_conns[i]['open'] = ''

            elif data['TYPE'] == "SOFT_CLOSE":
                #if len(data['PORT']) > 0:
                #    team_connections[data['PORT']].remove(conn)
                msg_conns[i]['open'] = ''

        connections.set_msg_conns(msg_conns)
        connections.set_team_conns(team_connections)
    
    #print("message stuff here?")
    conn.close()


# send new image frame to each of the connections in img_conns
# TODO - figure out how to remove img connection on close client-side
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


# separate thread to accept incoming image connections and append to img_conns
def accept_image_conns(image_s, connections):
    while True:
        img_conn, addr = image_s.accept()
        
        ics = connections.get_img_conns()
        ics.append({'conn': img_conn, 'addr': addr})
        connections.set_img_conns(ics)

        img_conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=newframe\r\n\r\n')
        #print(f'image_conns = {ics}\n')

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
        message_connections.append({'conn': msg_conn, 'addr': addr, 'open': ''})
        #message_connections.append({'conn': msg_conn, 'addr': addr})
        connections.set_msg_conns(message_connections)
        #print(f'message_conns = {message_connections}\n')

        # send initial json stuff and initial message to website
        #msg_conn.sendall(json.dumps({"TYPE": "PORT_LIST", "CONTENT": connections.get_udp_conns()}).encode())
        #start_new_thread(rec_msg, (msg_conn, connections, ))
        start_new_thread(rec_msg, (msg_conn, connections, ))

    

