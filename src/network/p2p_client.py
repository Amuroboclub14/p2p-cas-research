# Simple TCP server
import socket
srv = socket.socket()
srv.bind(('0.0.0.0', 9000))
srv.listen(1)
while True:
    conn, addr = srv.accept()
    msg = conn.recv(1024).decode()
    print(f'Received: {msg}')
    # Logic to send list of hashes or file bytes
    conn.close()
