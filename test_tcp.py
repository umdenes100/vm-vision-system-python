import socket
import threading
from _thread import *
import json
import time

image_frame_list = []
connections = []
message_connections = []
image_connections = []
udp_connections = {}

def udpthread(conn):
    print("udp thread started")
    while 1:
        data, addr = conn.recvfrom(1024)
        ip, port = addr

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
            
            send_message(udp_connections, 'PORT_LIST') # sends new port list to each connection
            send_message(str(int(time.time())), 'START') # send start command to msg server

            # TODO - return the destination - OpenCV
            
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
            send_message(get_mission_message(curr, udp_connections[ip]['MISSION'], message), 'MISSION')
            data_to_send = b'\x07'
        
        # DEBUG
        elif second == 8:
            msg = data[2:].decode()
            send_message(msg, 'DEBUG') # send debug message to msg server
            print(f"Debug message = {msg}")

        conn.sendto(data_to_send, addr)
        #print(f'ip = {ip} --- data = {data} --- sec = {second}')

def send_message(msgi, m_type):
    # send message to each connection in list
    json_stuff = json.dumps({'TYPE': m_type, 'CONTENT': msg})
    for d in connections:
        conn = d['msg']
        conn.sendall(json_stuffi.encode())

# TODO - figure out what we need to do when JavaScript sends a message back!
def rec_msg(conn):
    conn.sendall(b"initial message hehe")
    #stuff = json.dumps({'TYPE': 'DEBUG', 'CONTENT': })
    print("message stuff here?")
    conn.close()

# TODO
# check if connection is still alive --- this might be useful for killing old connections
# what is a way to do this efficiently without disrupting?
'''
def check_conn_list():
    for d in range(len(connections)):
        conn = connections[d]['msg']
        try:
            conn.sendall(b'test')
        except:
            connections = connections[0:d] + connections[d+1:]
'''

# send new image frame to each of the connections
def send_frame(frame):
    print("sending image frame")
    
    # ONE WAY image service
    # on new frame, send JPEG byte array to each connection

    data = b'--newframe\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
    data += frame.encode()

    for d in connections:
        # send frame
        conn = d['img']
        conn.sendall(data)
    
def main():
    udp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_s.bind(("", 7755))
    start_new_thread(udpthread, (udp_s, ))

    message_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    message_s.bind(("", 9000))
    image_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    image_s.bind(("", 8080))

    message_s.listen()
    image_s.listen()

    while True:
        msg_conn, addr = message_s.accept()
        img_conn, addr2 = image_s.accept()
        connections.append({'msg': msg_conn, 'img': img_conn})
        print(f'conns = {connections}\n')

        # send initial image HTTP stuff and initial message to website
        img_conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=newframe\r\n\r\n')
        msg_conn.sendall(json.dumps({"TYPE": "PORT_LIST", "CONTENT": udp_connections}).encode())

        start_new_thread(rec_msg, (msg_conn, ))
        #start_new_thread(image_)

if __name__ == '__main__':
    main()
