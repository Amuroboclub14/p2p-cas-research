#!/usr/bin/env python3
"""
P2P Peer Manager - Handles peer discovery and communication using DHT.
Each node acts as both client and server.
"""

import asyncio
import json
import hashlib
import os
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from src.dht.kademlia import KademliaNode


@dataclass
class PeerInfo:
    """Information about a peer in the network"""
    node_id: str
    ip: str
    port: int
    chunks: Set[str] = field(default_factory=set)  # Chunk hashes this peer has
    last_seen: float = field(default_factory=lambda: __import__('time').time())
    
    def __hash__(self):
        return hash((self.node_id, self.ip, self.port))
    
    def __eq__(self, other):
        if not isinstance(other, PeerInfo):
            return False
        return self.node_id == other.node_id and self.ip == other.ip and self.port == other.port


@dataclass
class FileMetadata:
    """Metadata about a file in the network"""
    file_hash: str
    original_name: str
    size: int
    data_chunks: List[str]  # List of chunk hashes
    parity_chunks: List[str]  # List of parity chunk hashes (for FEC)
    peers_with_metadata: Set[str] = field(default_factory=set)  # Node IDs that have this file's metadata


class P2PPeerManager:
    """
    Manages peer discovery, chunk location, and multi-peer downloads.
    Uses DHT to find peers and track which chunks they have.
    """
    
    def __init__(
        self,
        dht_node: KademliaNode,
        local_node_id: str,
        local_ip: str,
        local_port: int,
        storage_dir: str
    ):
        """
        Initialize the peer manager.
        
        Args:
            dht_node: KademliaNode instance for DHT operations
            local_node_id: This node's unique ID
            local_ip: This node's IP address
            local_port: This node's listening port
            storage_dir: Directory where chunks are stored
        """
        self.dht_node = dht_node
        self.local_node_id = local_node_id
        self.local_ip = local_ip
        self.local_port = local_port
        self.storage_dir = storage_dir
        
        # Tracking
        self.known_peers: Dict[str, PeerInfo] = {}  # node_id -> PeerInfo
        self.file_metadata: Dict[str, FileMetadata] = {}  # file_hash -> FileMetadata
        self.local_chunks: Set[str] = set()  # Chunks this node has
        
    async def load_local_chunks(self):
        """Scan storage directory and load list of chunks we have"""
        self.local_chunks.clear()
        
        if not os.path.exists(self.storage_dir):
            return
        
        for filename in os.listdir(self.storage_dir):
            filepath = os.path.join(self.storage_dir, filename)
            if os.path.isfile(filepath) and filename != "cas_index.json" and filename != "dht_storage.json":
                self.local_chunks.add(filename)
    
    async def register_chunks_in_dht(self, chunk_hashes: List[str]):
        """
        Register chunks in DHT so other peers can find them.
        
        Args:
            chunk_hashes: List of chunk hashes to register
        """
        peer_info = {
            "node_id": self.local_node_id,
            "ip": self.local_ip,
            "port": self.local_port
        }
        
        for chunk_hash in chunk_hashes:
            try:
                await self.dht_node.set(chunk_hash, peer_info)
                self.local_chunks.add(chunk_hash)
                print(f"[DHT] Registered chunk: {chunk_hash[:8]}...")
            except Exception as e:
                print(f"[ERROR] Failed to register chunk {chunk_hash}: {e}")
    
    async def find_peers_with_chunk(self, chunk_hash: str) -> List[PeerInfo]:
        """
        Find all peers that have a specific chunk using DHT.
        
        Args:
            chunk_hash: Hash of the chunk to find
            
        Returns:
            List of PeerInfo objects that have this chunk
        """
        try:
            result = await self.dht_node.get(chunk_hash)
            if result:
                peer = PeerInfo(
                    node_id=result.get("node_id"),
                    ip=result.get("ip"),
                    port=result.get("port")
                )
                peer.chunks.add(chunk_hash)
                
                # Update our peer tracking
                if peer.node_id not in self.known_peers:
                    self.known_peers[peer.node_id] = peer
                else:
                    self.known_peers[peer.node_id].chunks.add(chunk_hash)
                
                return [peer]
            return []
        except Exception as e:
            print(f"[ERROR] DHT lookup failed for chunk {chunk_hash}: {e}")
            return []
    
    async def find_peers_with_chunks(self, chunk_hashes: List[str]) -> Dict[str, List[PeerInfo]]:
        """
        Find peers for multiple chunks in parallel.
        
        Args:
            chunk_hashes: List of chunk hashes to find
            
        Returns:
            Dictionary mapping chunk_hash -> List[PeerInfo]
        """
        tasks = [self.find_peers_with_chunk(ch) for ch in chunk_hashes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        chunk_to_peers = {}
        for chunk_hash, result in zip(chunk_hashes, results):
            if isinstance(result, Exception):
                chunk_to_peers[chunk_hash] = []
            else:
                chunk_to_peers[chunk_hash] = result
        
        return chunk_to_peers
    
    async def publish_file_metadata(self, file_metadata: FileMetadata):
        """
        Publish file metadata to DHT so other peers can discover files.
        Creates a "files" DHT key that maps to available files.
        
        Args:
            file_metadata: FileMetadata object to publish
        """
        try:
            # Store file metadata under a special key
            metadata_key = f"file_metadata:{file_metadata.file_hash}"
            metadata_dict = {
                "file_hash": file_metadata.file_hash,
                "original_name": file_metadata.original_name,
                "size": file_metadata.size,
                "data_chunks": file_metadata.data_chunks,
                "parity_chunks": file_metadata.parity_chunks,
                "published_by": self.local_node_id,
                "ip": self.local_ip,
                "port": self.local_port
            }
            
            await self.dht_node.set(metadata_key, metadata_dict)
            print(f"[DHT] Published file metadata: {file_metadata.original_name}")
        except Exception as e:
            print(f"[ERROR] Failed to publish file metadata: {e}")
    
    async def discover_file(self, file_hash: str) -> Optional[FileMetadata]:
        """
        Discover file metadata from DHT.
        
        Args:
            file_hash: Hash of the file to discover
            
        Returns:
            FileMetadata if found, None otherwise
        """
        try:
            metadata_key = f"file_metadata:{file_hash}"
            result = await self.dht_node.get(metadata_key)
            
            if result:
                file_meta = FileMetadata(
                    file_hash=result.get("file_hash"),
                    original_name=result.get("original_name"),
                    size=result.get("size"),
                    data_chunks=result.get("data_chunks", []),
                    parity_chunks=result.get("parity_chunks", [])
                )
                self.file_metadata[file_hash] = file_meta
                return file_meta
            return None
        except Exception as e:
            print(f"[ERROR] Failed to discover file {file_hash}: {e}")
            return None
    
    async def list_available_files(self) -> List[FileMetadata]:
        """
        Query DHT for all available files (broadcast search).
        Note: In real DHT, you'd use iterative search to find file* keys.
        
        Returns:
            List of discovered file metadata
        """
        # This is a simplified version - in production, you'd iterate through DHT
        return list(self.file_metadata.values())
    
    def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        """Get peer info by node ID"""
        return self.known_peers.get(node_id)
    
    def add_peer(self, peer: PeerInfo) -> None:
        """Add or update a peer in our tracking"""
        if peer.node_id not in self.known_peers:
            self.known_peers[peer.node_id] = peer
        else:
            self.known_peers[peer.node_id].chunks.update(peer.chunks)
    
    def get_peers_with_capacity(self, min_chunks: int = 0) -> List[PeerInfo]:
        """Get list of peers sorted by number of chunks they have"""
        peers = list(self.known_peers.values())
        return sorted(peers, key=lambda p: len(p.chunks), reverse=True)
