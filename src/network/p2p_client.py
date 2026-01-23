#!/usr/bin/env python3
import json
import socket
import threading
import sys


def receive_messages(sock):
    receiving_file = False
    file = None

    try:
        while True:
            data = sock.recv(4096)
            if not data:
                print("\n[INFO] Server disconnected")
                break

            # try decoding as text
            msg = None
            if not receiving_file:
                try:
                    msg = data.decode()
                except UnicodeDecodeError:
                    pass


            #parsing JSON (metadata)
            meta = None
            if msg:
                try:
                    meta = json.loads(msg)
                except json.JSONDecodeError:
                    meta = None

            # file start
            if meta and meta.get("type") == "FILE_START":
                filename = meta.get("name", "received_file")
                size = meta.get("size", 0)

                print(f"\n[INFO] Receiving file: {filename} ({size} bytes)")
                file = open(filename, "wb")
                receiving_file = True
                continue

            # file end
            if meta and meta.get("type") == "FILE_END":
                if file:
                    file.close()
                file = None
                receiving_file = False
                print("[INFO] File transfer completed\n")
                continue

            # file data
            if receiving_file:
                file.write(data)
                continue

            # normal message
            elif msg:
                print("\n[SERVER]:", msg)
                print("[YOU]: ", end="", flush=True)

    except Exception as e:
        print(f"\n[ERROR] Receiving message: {e}")
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
            sock.send(msg.encode())
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
