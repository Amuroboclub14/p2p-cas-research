#!/usr/bin/env python3
import socket
import threading
import sys


def receive_messages(conn, addr):

    print(f"[INFO] Connected to {addr}")
    try:
        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                print(f"[INFO] Client {addr} disconnected")
                break
            print(f"\n[CLIENT]: {msg}")
            print("[YOU]: ", end="", flush=True)
    except Exception as e:
        print(f"\n[ERROR] Receiving message: {e}")
    finally:
        conn.close()


def send_messages(conn):

    try:
        while True:
            msg = input("[YOU]: ")
            if msg.lower() == "quit":
                print("[INFO] Closing connection...")
                conn.close()
                sys.exit(0)
            conn.send(msg.encode())
    except Exception as e:
        print(f"\n[ERROR] Sending message: {e}")
        conn.close()


def main():

    HOST = "0.0.0.0"
    PORT = 9000

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        srv.bind((HOST, PORT))
        srv.listen(1)
        print(f"[INFO] Server listening on {HOST}:{PORT}")
        print("[INFO] Waiting for client connection...")

        conn, addr = srv.accept()

        # Start threads for sending and receiving
        recv_thread = threading.Thread(
            target=receive_messages, args=(conn, addr), daemon=True
        )
        send_thread = threading.Thread(target=send_messages, args=(conn,), daemon=True)

        recv_thread.start()
        send_thread.start()

        # Keep main thread alive
        recv_thread.join()
        send_thread.join()

    except KeyboardInterrupt:
        print("\n[INFO] Server shutting down...")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
