#!/usr/bin/env python3
import json
import socket
import threading
import sys


def receive_messages(sock):
    file = None

    try:
        while True:
            # 1️read metadata line
            meta_raw = b""
            while not meta_raw.endswith(b"\n"):
                chunk = sock.recv(1)
                if not chunk:
                    print("\n[INFO] Server disconnected")
                    return
                meta_raw += chunk

            meta = json.loads(meta_raw.decode().strip())

            # file start
            if meta.get("type") == "FILE_START":
                filename = meta.get("name", "received_file")
                remaining = meta.get("size", 0)

                print(f"[INFO] Receiving file: {filename} ({remaining} bytes)")
                file = open(filename, "wb")

                # exact file bytes
                while remaining > 0:
                    data = sock.recv(min(4096, remaining))
                    if not data:
                        raise Exception("Connection lost during file transfer")
                    file.write(data)
                    remaining -= len(data)

                file.close()
                file = None
                print("[INFO] File transfer completed\n")
                print("[YOU]:", end = "", flush=True)
            

            # normal message
            else:
                print("\n[SERVER]:", meta)
                print("[YOU]:",end = "", flush=True)

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        if file:
            file.close()
        sock.close()







def send_messages(sock):

    try:
        while True:
            msg = input("[YOU]: ")
            if msg.lower() == "quit":
                print("[INFO] Closing connection...")
                sock.close()
                sys.exit(0)
            sock.send((msg + "\n").encode())
    except Exception as e:
        print(f"\n[ERROR] Sending message: {e}")
        sock.close()


def main():
    """Main client function"""
    HOST = "127.0.0.1"
    PORT = 9000

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        print(f"[INFO] Connecting to server at {HOST}:{PORT}...")
        sock.connect((HOST, PORT))
        print("[INFO] Connected to server!")
        print("[INFO] Type 'quit' to exit\n")

        # Start threads for sending and receiving
        recv_thread = threading.Thread(
            target=receive_messages, args=(sock,), daemon=True
        )
        send_thread = threading.Thread(target=send_messages, args=(sock,), daemon=True)

        recv_thread.start()
        send_thread.start()

        # Keep main thread alive
        recv_thread.join()
        send_thread.join()

    except ConnectionRefusedError:
        print("[ERROR] Could not connect to server. Make sure the server is running.")
    except KeyboardInterrupt:
        print("\n[INFO] Client shutting down...")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        sock.close()


if __name__ == "__main__":
    main()





