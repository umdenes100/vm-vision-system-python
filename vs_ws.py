import struct

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

# send to websocket
def send_text(data, conn, opcode=OPCODE_TEXT):
    header  = bytearray()
    payload = str(data).encode()
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

    print(f'header = {header}\npayload = {payload}\n')
    header.extend(payload)
    conn.sendall(header)

# Decode the websocket packet and send actual message & opcode back
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
