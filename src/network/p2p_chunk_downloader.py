#!/usr/bin/env python3
"""
P2P Chunk Downloader - Downloads chunks from multiple peers in parallel.
Similar to BitTorrent piece downloading strategy.
"""

import asyncio
import socket
import hashlib
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ChunkStatus(Enum):
    """Status of a chunk download"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ChunkDownloadTask:
    """Information about a chunk download task"""
    chunk_hash: str
    peer_ip: str
    peer_port: int
    status: ChunkStatus = ChunkStatus.PENDING
    data: bytes = b""
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3


class P2PChunkDownloader:
    """
    Handles downloading chunks from multiple peers using TCP connection pooling.
    Supports parallel downloads from different peers.
    """
    
    def __init__(self, storage_dir: str, timeout: int = 30, max_connections: int = 5):
        """
        Initialize the chunk downloader.
        
        Args:
            storage_dir: Directory to save downloaded chunks
            timeout: Socket timeout in seconds
            max_connections: Maximum concurrent connections
        """
        self.storage_dir = storage_dir
        self.timeout = timeout
        self.max_connections = max_connections
        self.semaphore = asyncio.Semaphore(max_connections)
    
    async def download_chunk(
        self,
        chunk_hash: str,
        peer_ip: str,
        peer_port: int
    ) -> Optional[bytes]:
        """
        Download a single chunk from a peer.
        
        Args:
            chunk_hash: Hash of the chunk to download
            peer_ip: IP address of the peer
            peer_port: Port of the peer
            
        Returns:
            Chunk data if successful, None if failed
        """
        async with self.semaphore:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(peer_ip, peer_port),
                    timeout=self.timeout
                )
                
                # Send GET_CHUNK request
                request = {
                    "type": "GET_CHUNK",
                    "chunk_hash": chunk_hash
                }
                import json
                writer.write((json.dumps(request) + "\n").encode())
                await writer.drain()
                
                # Receive chunk size
                size_line = b""
                while not size_line.endswith(b"\n"):
                    chunk = await asyncio.wait_for(
                        reader.readexactly(1),
                        timeout=self.timeout
                    )
                    if not chunk:
                        raise Exception("Connection closed")
                    size_line += chunk
                
                import json
                size_data = json.loads(size_line.decode().strip())
                
                if size_data.get("type") == "ERROR":
                    print(f"[DOWNLOAD] Peer {peer_ip}:{peer_port} doesn't have chunk {chunk_hash[:8]}...")
                    return None
                
                chunk_size = size_data.get("size", 0)
                if chunk_size <= 0:
                    raise Exception("Invalid chunk size")
                
                # Receive chunk data
                chunk_data = await asyncio.wait_for(
                    reader.readexactly(chunk_size),
                    timeout=self.timeout
                )
                
                # Verify hash
                calculated_hash = hashlib.sha256(chunk_data).hexdigest()
                if calculated_hash != chunk_hash:
                    raise Exception(f"Hash mismatch: expected {chunk_hash}, got {calculated_hash}")
                
                writer.close()
                await writer.wait_closed()
                
                print(f"[DOWNLOAD] ✓ Chunk {chunk_hash[:8]}... from {peer_ip}:{peer_port}")
                return chunk_data
                
            except asyncio.TimeoutError:
                print(f"[DOWNLOAD] ✗ Timeout downloading from {peer_ip}:{peer_port}")
                return None
            except Exception as e:
                print(f"[DOWNLOAD] ✗ Error from {peer_ip}:{peer_port}: {e}")
                return None
    
    async def download_chunks_parallel(
        self,
        chunk_peers: Dict[str, List[Tuple[str, int]]]
    ) -> Dict[str, Optional[bytes]]:
        """
        Download multiple chunks from different peers in parallel.
        Uses first available peer for each chunk.
        
        Args:
            chunk_peers: Dict mapping chunk_hash -> List[(peer_ip, peer_port)]
            
        Returns:
            Dict mapping chunk_hash -> chunk_data (or None if failed)
        """
        tasks = []
        chunk_order = list(chunk_peers.keys())
        
        for chunk_hash, peers in chunk_peers.items():
            if peers:
                peer_ip, peer_port = peers[0]  # Try first peer
                tasks.append(self.download_chunk(chunk_hash, peer_ip, peer_port))
            else:
                tasks.append(asyncio.sleep(0))  # No peers available
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        chunk_data = {}
        for chunk_hash, result in zip(chunk_order, results):
            if isinstance(result, Exception):
                chunk_data[chunk_hash] = None
            else:
                chunk_data[chunk_hash] = result
        
        return chunk_data
    
    async def download_file_chunks(
        self,
        chunk_peers: Dict[str, List[Tuple[str, int]]],
        save_dir: str,
        progress_callback=None
    ) -> bool:
        """
        Download all chunks for a file and save them locally.
        
        Args:
            chunk_peers: Dict mapping chunk_hash -> List[(peer_ip, peer_port)]
            save_dir: Directory to save chunks
            progress_callback: Optional callback for progress updates
            
        Returns:
            True if all chunks downloaded successfully, False otherwise
        """
        import os
        os.makedirs(save_dir, exist_ok=True)
        
        results = await self.download_chunks_parallel(chunk_peers)
        
        success_count = 0
        for chunk_hash, chunk_data in results.items():
            if chunk_data:
                chunk_path = os.path.join(save_dir, chunk_hash)
                with open(chunk_path, "wb") as f:
                    f.write(chunk_data)
                success_count += 1
                
                if progress_callback:
                    progress_callback(chunk_hash, True)
            else:
                if progress_callback:
                    progress_callback(chunk_hash, False)
        
        return success_count == len(chunk_peers)
    
    async def download_with_retry(
        self,
        chunk_hash: str,
        peers: List[Tuple[str, int]],
        max_retries: int = 3
    ) -> Optional[bytes]:
        """
        Download a chunk with fallback to alternative peers on failure.
        
        Args:
            chunk_hash: Hash of chunk to download
            peers: List of (ip, port) tuples to try in order
            max_retries: Maximum number of retries
            
        Returns:
            Chunk data if successful, None if all peers failed
        """
        for attempt in range(min(max_retries, len(peers))):
            peer_ip, peer_port = peers[attempt]
            chunk_data = await self.download_chunk(chunk_hash, peer_ip, peer_port)
            
            if chunk_data:
                return chunk_data
        
        return None
