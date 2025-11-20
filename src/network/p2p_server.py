#!/usr/bin/env python3
import socket
import threading
import sys

# Global list to keep track of all connected clients
clients = []
clients_lock = threading.Lock()


def broadcast_message(message, sender_addr):
    """Send message to all connected clients except the sender"""
    with clients_lock:
        for client_conn, client_addr in clients:
            if client_addr != sender_addr:
                try:
                    client_conn.send(message.encode())
                except Exception as e:
                    print(f"[ERROR] Failed to send to {client_addr}: {e}")


def handle_client(conn, addr):
    """Handle communication with a single client"""
    print(f"[INFO] Client {addr} connected")

    # Add client to the list
    with clients_lock:
        clients.append((conn, addr))

    try:
        while True:
            msg = conn.recv(1024).decode()
            if not msg:
                print(f"[INFO] Client {addr} disconnected")
                break
            print(f"[CLIENT {addr}]: {msg}")
            # Broadcast to all other clients
            broadcast_message(f"[CLIENT {addr}]: {msg}", addr)
    except Exception as e:
        print(f"[ERROR] Client {addr}: {e}")
    finally:
        # Remove client from the list
        with clients_lock:
            clients.remove((conn, addr))
        conn.close()
        print(f"[INFO] Client {addr} removed. Active clients: {len(clients)}")


def accept_clients(srv):
    """Continuously accept new client connections"""
    while True:
        try:
            conn, addr = srv.accept()
            # Start a new thread for each client
            client_thread = threading.Thread(
                target=handle_client, args=(conn, addr), daemon=True
            )
            client_thread.start()
        except Exception as e:
            print(f"[ERROR] Accepting client: {e}")
            break


def server_input():
    """Handle server-side input to broadcast messages"""
    while True:
        try:
            msg = input()
            if msg.lower() == "quit":
                print("[INFO] Server shutting down...")
                sys.exit(0)
            # Broadcast server message to all clients
            with clients_lock:
                for client_conn, client_addr in clients:
                    try:
                        client_conn.send(f"[SERVER]: {msg}".encode())
                    except Exception as e:
                        print(f"[ERROR] Failed to send to {client_addr}: {e}")
        except EOFError:
            break
        except Exception as e:
            print(f"[ERROR] Server input: {e}")


def main():
    HOST = "0.0.0.0"
    PORT = 9000

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        srv.bind((HOST, PORT))
        srv.listen(5)  # Allow up to 5 pending connections
        print(f"[INFO] Server listening on {HOST}:{PORT}")
        print("[INFO] Waiting for client connections...")
        print("[INFO] Type messages to broadcast to all clients, or 'quit' to exit\n")

        # Start thread to accept clients
        accept_thread = threading.Thread(
            target=accept_clients, args=(srv,), daemon=True
        )
        accept_thread.start()

        # Handle server input in main thread
        server_input()

    except KeyboardInterrupt:
        print("\n[INFO] Server shutting down...")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
