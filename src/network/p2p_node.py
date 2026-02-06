#!/usr/bin/env python3
"""
P2P Node - Hybrid server/client node that serves chunks and downloads from peers.
Acts as both a file server and client in the P2P network.
"""

import socket
import threading
import asyncio
import json
import os
import logging
from typing import Optional, Dict, Set
from src.dht.kademlia import KademliaNode
from src.network.p2p_peer_manager import P2PPeerManager
from src.network.p2p_chunk_downloader import P2PChunkDownloader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class P2PNode:
    """
    A peer in the P2P network that both serves and downloads chunks.
    """
    
    def __init__(
        self,
        node_id: str,
        server_host: str,
        server_port: int,
        dht_port: int,
        storage_dir: str,
        max_concurrent_downloads: int = 5
    ):
        """
        Initialize a P2P node.
        
        Args:
            node_id: Unique identifier for this node
            server_host: Host to bind server socket to
            server_port: Port for serving chunks
            dht_port: Port for DHT communication
            storage_dir: Directory for storing chunks
            max_concurrent_downloads: Max parallel chunk downloads
        """
        self.node_id = node_id
        self.server_host = server_host
        self.server_port = server_port
        self.dht_port = dht_port
        self.storage_dir = storage_dir
        
        # Components
        self.dht_node: Optional[KademliaNode] = None
        self.peer_manager: Optional[P2PPeerManager] = None
        self.chunk_downloader: Optional[P2PChunkDownloader] = None
        
        # Server state
        self.server_socket: Optional[socket.socket] = None
        self.server_running = False
        self.client_connections: Set[tuple] = set()
        self.connections_lock = threading.Lock()
        
        # Event loop
        self.loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def initialize(self):
        """Initialize all components"""
        logger.info(f"[P2P] Initializing node {self.node_id}")
        
        # Create DHT node
        self.dht_node = KademliaNode(self.server_host, self.dht_port)
        await self.dht_node.start()
        
        # Try to bootstrap to existing network
        # In production, use known DHT nodes
        try:
            await self.dht_node.bootstrap([(self.server_host, self.dht_port)])
            logger.info("[DHT] Node bootstrapped")
        except Exception as e:
            logger.warning(f"[DHT] Bootstrap failed: {e}")
        
        # Create peer manager
        self.peer_manager = P2PPeerManager(
            self.dht_node,
            self.node_id,
            self.server_host,
            self.server_port,
            self.storage_dir
        )
        
        # Load local chunks
        await self.peer_manager.load_local_chunks()
        logger.info(f"[STORAGE] Loaded {len(self.peer_manager.local_chunks)} local chunks")
        
        # Register local chunks in DHT
        await self.peer_manager.register_chunks_in_dht(
            list(self.peer_manager.local_chunks)
        )

        # Publish file metadata for any files in our local CAS index so clients can discover them
        try:
            index_path = os.path.join(self.storage_dir, "cas_index.json")
            if os.path.exists(index_path):
                with open(index_path, "r") as f:
                    index = json.load(f)

                for file_hash, meta in index.items():
                    # Build FileMetadata dataclass from peer manager definition
                    try:
                        file_meta = self.peer_manager.FileMetadata(
                            file_hash=file_hash,
                            original_name=meta.get("original_name"),
                            size=meta.get("size"),
                            data_chunks=meta.get("data_chunks", []),
                            parity_chunks=meta.get("parity_chunks", [])
                        )
                    except Exception:
                        # Fallback: construct using the dataclass from module
                        from src.network.p2p_peer_manager import FileMetadata as _FM
                        file_meta = _FM(
                            file_hash=file_hash,
                            original_name=meta.get("original_name"),
                            size=meta.get("size"),
                            data_chunks=meta.get("data_chunks", []),
                            parity_chunks=meta.get("parity_chunks", [])
                        )

                    # Publish metadata to DHT
                    await self.peer_manager.publish_file_metadata(file_meta)
        except Exception as e:
            logger.warning(f"[DHT] Failed publishing local file metadata: {e}")
        
        # Create chunk downloader
        self.chunk_downloader = P2PChunkDownloader(self.storage_dir)
        
        logger.info("[P2P] Node initialization complete")
    
    def start_server(self):
        """Start the TCP server for serving chunks (runs in thread)"""
        def run_server():
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind((self.server_host, self.server_port))
                self.server_socket.listen(10)
                
                self.server_running = True
                logger.info(f"[SERVER] Listening on {self.server_host}:{self.server_port}")
                
                while self.server_running:
                    try:
                        self.server_socket.settimeout(1.0)
                        conn, addr = self.server_socket.accept()
                        
                        # Handle client in new thread
                        client_thread = threading.Thread(
                            target=self._handle_client,
                            args=(conn, addr),
                            daemon=True
                        )
                        client_thread.start()
                        
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"[SERVER] Accept error: {e}")
                        break
            
            except Exception as e:
                logger.error(f"[SERVER] Error: {e}")
            finally:
                if self.server_socket:
                    self.server_socket.close()
                self.server_running = False
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
    
    def _handle_client(self, conn: socket.socket, addr: tuple):
        """Handle a client connection requesting chunks or file metadata"""
        logger.info(f"[SERVER] Client connected: {addr}")
        
        try:
            with self.connections_lock:
                self.client_connections.add(addr)
            
            while True:
                # Read request header (JSON)
                request_data = b""
                while not request_data.endswith(b"\n"):
                    chunk = conn.recv(1)
                    if not chunk:
                        break
                    request_data += chunk
                
                if not request_data:
                    break
                
                request = json.loads(request_data.decode().strip())
                request_type = request.get("type")
                
                # ===== GET_CHUNK =====
                if request_type == "GET_CHUNK":
                    chunk_hash = request.get("chunk_hash")
                    self._serve_chunk(conn, chunk_hash)
                
                # ===== LIST_FILES =====
                elif request_type == "LIST_FILES":
                    self._serve_file_list(conn)
                
                # ===== GET_FILE_METADATA =====
                elif request_type == "GET_FILE_METADATA":
                    file_hash = request.get("file_hash")
                    self._serve_file_metadata(conn, file_hash)
                
                else:
                    conn.sendall(json.dumps({"type": "ERROR", "message": "Unknown request"}).encode() + b"\n")
        
        except Exception as e:
            logger.error(f"[SERVER] Error handling {addr}: {e}")
        
        finally:
            conn.close()
            with self.connections_lock:
                self.client_connections.discard(addr)
            logger.info(f"[SERVER] Client disconnected: {addr}")
    
    def _serve_chunk(self, conn: socket.socket, chunk_hash: str):
        """Serve a chunk if we have it"""
        chunk_path = os.path.join(self.storage_dir, chunk_hash)
        
        try:
            if not os.path.exists(chunk_path):
                conn.sendall(json.dumps({"type": "ERROR"}).encode() + b"\n")
                return
            
            # Send size header
            chunk_size = os.path.getsize(chunk_path)
            conn.sendall(
                json.dumps({"type": "CHUNK_START", "size": chunk_size}).encode() + b"\n"
            )
            
            # Send chunk data
            with open(chunk_path, "rb") as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    conn.sendall(data)
            
            logger.info(f"[SERVER] Served chunk {chunk_hash[:8]}... to {conn.getpeername()}")
        
        except Exception as e:
            logger.error(f"[SERVER] Error serving chunk: {e}")
            try:
                conn.sendall(json.dumps({"type": "ERROR"}).encode() + b"\n")
            except:
                pass
    
    def _serve_file_list(self, conn: socket.socket):
        """Serve list of available files"""
        try:
            index_path = os.path.join(self.storage_dir, "cas_index.json")
            files = []
            
            if os.path.exists(index_path):
                with open(index_path, "r") as f:
                    index = json.load(f)
                
                for file_hash, meta in index.items():
                    files.append({
                        "name": meta.get("original_name"),
                        "hash": file_hash,
                        "size": meta.get("size"),
                        "available_on": self.node_id  # Which node has this
                    })
            
            conn.sendall(
                json.dumps({"type": "FILE_LIST", "files": files}).encode() + b"\n"
            )
        
        except Exception as e:
            logger.error(f"[SERVER] Error listing files: {e}")
            conn.sendall(json.dumps({"type": "ERROR"}).encode() + b"\n")
    
    def _serve_file_metadata(self, conn: socket.socket, file_hash: str):
        """Serve metadata for a specific file"""
        try:
            index_path = os.path.join(self.storage_dir, "cas_index.json")
            
            if not os.path.exists(index_path):
                conn.sendall(json.dumps({"type": "ERROR"}).encode() + b"\n")
                return
            
            with open(index_path, "r") as f:
                index = json.load(f)
            
            if file_hash not in index:
                conn.sendall(json.dumps({"type": "ERROR"}).encode() + b"\n")
                return
            
            meta = index[file_hash]
            conn.sendall(
                json.dumps({
                    "type": "FILE_METADATA",
                    "file_hash": file_hash,
                    "original_name": meta.get("original_name"),
                    "size": meta.get("size"),
                    "data_chunks": meta.get("data_chunks", []),
                    "parity_chunks": meta.get("parity_chunks", [])
                }).encode() + b"\n"
            )
        
        except Exception as e:
            logger.error(f"[SERVER] Error serving metadata: {e}")
            conn.sendall(json.dumps({"type": "ERROR"}).encode() + b"\n")
    
    async def download_file_from_peers(
        self,
        file_hash: str,
        output_dir: str
    ) -> bool:
        """
        Download a file by discovering chunks from peers via DHT.
        
        Args:
            file_hash: Hash of file to download
            output_dir: Directory to save chunks
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"[DOWNLOAD] Fetching file {file_hash[:8]}...")
        
        # Discover file metadata
        file_meta = await self.peer_manager.discover_file(file_hash)
        if not file_meta:
            logger.error(f"[DOWNLOAD] File not found in DHT")
            return False
        
        logger.info(f"[DOWNLOAD] Found file: {file_meta.original_name}")
        
        # Find peers for all chunks
        all_chunks = file_meta.data_chunks + file_meta.parity_chunks
        chunk_peers = await self.peer_manager.find_peers_with_chunks(all_chunks)
        
        # Download data chunks (parity is optional)
        logger.info(f"[DOWNLOAD] Downloading {len(file_meta.data_chunks)} data chunks...")
        download_peers = {ch: chunk_peers.get(ch, []) for ch in file_meta.data_chunks}
        
        success = await self.chunk_downloader.download_file_chunks(
            download_peers,
            output_dir
        )
        
        if success:
            logger.info(f"[DOWNLOAD] ✓ File downloaded successfully")
        else:
            logger.error(f"[DOWNLOAD] ✗ Some chunks failed to download")
        
        return success
    
    async def shutdown(self):
        """Shutdown the node"""
        logger.info("[P2P] Shutting down...")
        self.server_running = False
        
        if self.dht_node:
            await self.dht_node.stop()
        
        logger.info("[P2P] Shutdown complete")
