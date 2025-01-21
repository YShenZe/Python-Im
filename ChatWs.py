import socket
import threading
import base64
import hashlib
import json
import time

HOST = '127.0.0.1'
PORT = 5002

clients = []
chat_history = []

# 加载现有的聊天记录
try:
    with open('chat_history.json', 'r', encoding='utf-8') as file:
        chat_history = json.load(file)
except FileNotFoundError:
    pass

def decode_websocket_data(data):
    byte_array = bytearray(data)
    first_byte = byte_array[0]
    second_byte = byte_array[1]

    # 解析 WebSocket 数据
    payload_length = second_byte & 127
    mask_start = 2

    if payload_length == 126:
        payload_length = int.from_bytes(byte_array[2:4], byteorder='big')
        mask_start = 4
    elif payload_length == 127:
        payload_length = int.from_bytes(byte_array[2:10], byteorder='big')
        mask_start = 10

    # 解析掩码
    mask = byte_array[mask_start:mask_start+4]
    data_start = mask_start + 4

    # 解码数据
    unmasked_payload = b""
    for i in range(payload_length):
        unmasked_payload += bytes([byte_array[data_start + i] ^ mask[i % 4]])

    return unmasked_payload.decode('utf-8', errors='ignore')  # 使用忽略非法字符

def encode_websocket_data(payload):
    payload_bytes = payload.encode('utf-8')
    payload_length = len(payload_bytes)
    frame = bytearray()

    frame.append(0x81)  # FIN + opcode

    if payload_length <= 125:
        frame.append(payload_length)
    elif payload_length <= 65535:
        frame.append(126)
        frame.extend(payload_length.to_bytes(2, byteorder='big'))
    else:
        frame.append(127)
        frame.extend(payload_length.to_bytes(8, byteorder='big'))

    frame.extend(payload_bytes)
    return frame

def handle_client(conn, addr):
    print("Client connected:", addr)
    clients.append(conn)

    # 发送历史聊天记录
    if chat_history:
        conn.sendall(encode_websocket_data(json.dumps(chat_history)))

    while True:
        try:
            data = conn.recv(1024)
            if not data:
                break

            print(f"Raw data received: {data}")  # 打印原始数据
            decoded_data = decode_websocket_data(data)
            print(f"Decoded data: {decoded_data}")

            decoded_message = json.loads(decoded_data)
            if decoded_message.get('type') == 'message':
                message_entry = {
                    'user': decoded_message['user'],
                    'message': decoded_message['message'],
                    'time': decoded_message['time'],
                    'timestamp': int(time.time())
                }
                chat_history.append(message_entry)

                # 保存聊天记录到 JSON 文件
                with open('chat_history.json', 'w', encoding='utf-8') as file:
                    json.dump(chat_history, file, indent=4, ensure_ascii=False)

            response = encode_websocket_data(decoded_data)
            for client in clients:
                client.sendall(response)

        except (ConnectionResetError, ConnectionAbortedError) as e:
            print(f"Connection error: {e}")
            break

    print("Client disconnected:", addr)
    clients.remove(conn)
    conn.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)

    print(f"WebSocket server started at ws://{HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        handshake_data = conn.recv(1024).decode('utf-8')

        if 'Sec-WebSocket-Key' in handshake_data:
            key = handshake_data.split('Sec-WebSocket-Key: ')[1].split('\r\n')[0]
            accept_key = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('utf-8')).digest()).decode('utf-8')
            response_headers = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
            )
            conn.sendall(response_headers.encode('utf-8'))

            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.start()

if __name__ == "__main__":
    start_server()
