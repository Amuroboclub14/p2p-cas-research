#!/usr/bin/env python3
import socket
import threading
import sys


def receive_messages(sock):
    try:
        while True:
            msg = sock.recv(1024).decode()
            if not msg:
                print("\n[INFO] Server disconnected")
                break

            print("\n server response")
            print(msg)
            print("[YOU]: ", end="", flush=True)

    except Exception as e:
        print(f"\n[ERROR] Receiving message: {e}")
    finally:
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
