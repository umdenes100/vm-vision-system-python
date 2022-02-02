import socket

udpport = 7755
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("", udpport))
print(f"waiting on port {port}")
while 1:
    data, addr = s.recvfrom(1024)
    print(f'data = {data}')
