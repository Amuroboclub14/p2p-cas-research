#!/usr/bin/env python3
import socket
import threading
import sys
import json
import os
from src.network.dh_utils import (
    generate_dh_parameters, generate_private_key, generate_shared_key )
DH_PARAMS = generate_dh_parameters()

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
    print(f"[INFO] Client {addr} connected")

# Diffie hellman handshake (server side)
    from cryptography.hazmat.primitives import serialization
    # send parameters to client
    params_bytes = DH_PARAMS.parameter_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.ParameterFormat.PKCS3
    )
    conn.sendall(params_bytes)
    server_private_key = generate_private_key(DH_PARAMS)
    server_public_key = server_private_key.public_key()
    # receive client's public key
    client_pub_bytes = conn.recv(2048)
    client_public_key = serialization.load_pem_public_key(client_pub_bytes)
    # send server's public key
    server_pub_bytes = server_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    conn.sendall(server_pub_bytes)
    shared_key = generate_shared_key(server_private_key, client_public_key)
    print(f"[SECURITY] Diffie Hellman handshake completed on SERVER")
    with clients_lock:
        clients.append((conn, addr))

    try:
        while True:
            msg = conn.recv(1024)
            if not msg:
                print(f"[INFO] Client {addr} disconnected")
                break

            try:
                data = json.loads(msg.decode())
            except json.JSONDecodeError:
                continue

            # ============ LIST FILES ============
            if data.get("type") == "LIST_FILES":
                index_path = os.path.join(
                    os.path.dirname(__file__),
                    "..", "..", "storage", "hashed_files",
                    "cas_index.json"
                )

                files = []
                if os.path.exists(index_path):
                    with open(index_path, "r") as f:
                        index = json.load(f)

                    for h, meta in index.items():
                        files.append({
                            "name": meta["original_name"],
                            "hash": h,
                            "size": meta["size"]
                        })

                conn.sendall((json.dumps({
                    "type": "FILE_LIST",
                    "files": files
                }) + "\n").encode())

            # ============ GET FILE ============
            elif data.get("type") == "GET_FILE":
                file_hash = data.get("hash")

                storage_dir = os.path.join(
                    os.path.dirname(__file__),
                    "..", "..", "storage", "hashed_files"
                )
                index_path = os.path.join(storage_dir, "cas_index.json")

                if not os.path.exists(index_path):
                    conn.sendall(json.dumps({"type": "ERROR"}).encode())
                    continue

                with open(index_path, "r") as f:
                    index = json.load(f)

                if file_hash not in index:
                    conn.sendall(json.dumps({"type": "ERROR"}).encode())
                    continue

                meta = index[file_hash]

                # ---- FILE START ----
                conn.sendall(
                    (json.dumps({
                        "type": "FILE_START",
                        "name": meta["original_name"],
                        "size": meta["size"]
                    }) + "\n").encode()
                )

                print(f"[INFO] Sending {meta['original_name']} to {addr}")

                # ---- SEND FILE DATA (DATA CHUNKS ONLY) ----
                for chunk_hash in meta["data_chunks"]:
                    chunk_path = os.path.join(storage_dir, chunk_hash)

                    if not os.path.exists(chunk_path):
                        continue

                    with open(chunk_path, "rb") as cf:
                        while True:
                            data_bytes = cf.read(4096)
                            if not data_bytes:
                                break
                            conn.sendall(data_bytes)

                # ---- FILE END (🔥 THIS WAS MISSING 🔥) ----
                conn.sendall((json.dumps({
                    "type": "FILE_END"
                }) + "\n").encode())

                print(f"[INFO] File sent successfully to {addr}")

    except Exception as e:
        print(f"[ERROR] Client {addr}: {e}")

    finally:
        with clients_lock:
            if (conn, addr) in clients:
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
            # Skip empty messages
            if msg.strip():
                # Broadcast server message to all clients
                with clients_lock:
                    for client_conn, client_addr in clients:
                        try:
                            client_conn.send(f"{msg}".encode())
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
