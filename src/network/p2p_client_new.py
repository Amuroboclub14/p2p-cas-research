#!/usr/bin/env python3
"""
P2P Client - Downloads files from the P2P network using DHT discovery.
"""

import asyncio
import json
import sys
import logging
from typing import Optional
from src.dht.kademlia import KademliaNode
from src.network.p2p_peer_manager import P2PPeerManager
from src.network.p2p_chunk_downloader import P2PChunkDownloader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class P2PClient:
    """
    A client that downloads files from the P2P network.
    Uses DHT to discover peers and chunks.
    """
    
    def __init__(
        self,
        dht_bootstrap_nodes: list,
        download_dir: str = ".",
        max_concurrent: int = 5
    ):
        """
        Initialize P2P client.
        
        Args:
            dht_bootstrap_nodes: List of (ip, port) tuples for DHT bootstrap
            download_dir: Directory to save downloaded files
            max_concurrent: Max concurrent chunk downloads
        """
        self.dht_bootstrap_nodes = dht_bootstrap_nodes
        self.download_dir = download_dir
        
        self.dht_node: Optional[KademliaNode] = None
        self.peer_manager: Optional[P2PPeerManager] = None
        self.chunk_downloader: Optional[P2PChunkDownloader] = None
    
    async def initialize(self):
        """Initialize client components"""
        logger.info("[CLIENT] Initializing...")
        
        # Create DHT node (just for discovery, no serving)
        self.dht_node = KademliaNode("127.0.0.1", 0)  # 0 = random port
        await self.dht_node.start()
        
        # Bootstrap to network
        try:
            await self.dht_node.bootstrap(self.dht_bootstrap_nodes)
            logger.info("[DHT] Bootstrap successful")
        except Exception as e:
            logger.error(f"[DHT] Bootstrap failed: {e}")
            return False
        
        # Create peer manager (without local storage)
        import uuid
        client_id = str(uuid.uuid4())[:8]
        
        self.peer_manager = P2PPeerManager(
            self.dht_node,
            client_id,
            "127.0.0.1",
            0,  # Client doesn't serve
            self.download_dir
        )
        
        # Create downloader
        self.chunk_downloader = P2PChunkDownloader(self.download_dir)
        
        logger.info("[CLIENT] Initialization complete")
        return True
    
    async def list_files(self) -> list:
        """
        List all files available in the network.
        Note: This is simplified - real implementation would do DHT search.
        
        Returns:
            List of available files
        """
        logger.info("[CLIENT] Searching network for files...")
        # In production: iterate through DHT to find file_metadata:* keys
        available_files = await self.peer_manager.list_available_files()
        return available_files
    
    async def download_file(self, file_hash: str, output_name: Optional[str] = None) -> bool:
        """
        Download a file from the P2P network.
        
        Args:
            file_hash: Hash of file to download
            output_name: Optional custom output filename
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"[CLIENT] Downloading file {file_hash[:8]}...")
        
        # Discover file metadata from DHT
        file_meta = await self.peer_manager.discover_file(file_hash)
        if not file_meta:
            logger.error("[CLIENT] File not found in network")
            return False
        
        logger.info(f"[CLIENT] Found: {file_meta.original_name} ({file_meta.size} bytes)")
        
        # Find peers with chunks
        all_chunks = file_meta.data_chunks + file_meta.parity_chunks
        logger.info(f"[CLIENT] Finding peers for {len(file_meta.data_chunks)} data chunks...")
        
        chunk_peers = await self.peer_manager.find_peers_with_chunks(all_chunks)
        
        # Check if we can get all data chunks
        missing_chunks = []
        for chunk in file_meta.data_chunks:
            if not chunk_peers.get(chunk):
                missing_chunks.append(chunk)
        
        if missing_chunks:
            logger.warning(f"[CLIENT] Cannot find {len(missing_chunks)} chunks:")
            for ch in missing_chunks[:5]:  # Show first 5
                logger.warning(f"  - {ch[:8]}...")
            return False
        
        # Prepare download map: chunk_hash -> [(peer_ip, peer_port)]
        download_map = {}
        for chunk_hash, peers in chunk_peers.items():
            if chunk_hash in file_meta.data_chunks:  # Only download data chunks
                download_map[chunk_hash] = [(p.ip, p.port) for p in peers]
        
        # Download chunks
        logger.info(f"[CLIENT] Starting parallel download from {len(set(p[0] for peers in download_map.values() for p in peers))} peers...")
        
        import os
        os.makedirs(self.download_dir, exist_ok=True)
        
        success = await self.chunk_downloader.download_file_chunks(
            download_map,
            self.download_dir
        )
        
        if success:
            logger.info(f"[CLIENT] ✓ Download complete: {file_meta.original_name}")
        else:
            logger.error(f"[CLIENT] ✗ Download failed: missing chunks")
        
        return success
    
    async def shutdown(self):
        """Cleanup resources"""
        if self.dht_node:
            await self.dht_node.stop()
        logger.info("[CLIENT] Shutdown complete")


async def interactive_client():
    """Interactive client CLI"""
    
    # Bootstrap nodes - in production, use known nodes
    bootstrap_nodes = [("127.0.0.1", 8468)]
    
    client = P2PClient(bootstrap_nodes, download_dir="downloads")
    
    if not await client.initialize():
        logger.error("Failed to initialize client")
        return
    
    print("\n=== P2P File Sharing Client ===")
    print("Commands:")
    print("  list              - List available files")
    print("  download <hash>   - Download file by hash")
    print("  quit              - Exit")
    print()
    
    try:
        while True:
            try:
                cmd = input("client> ").strip()
                
                if not cmd:
                    continue
                
                parts = cmd.split(maxsplit=1)
                command = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None
                
                if command == "list":
                    files = await client.list_files()
                    if files:
                        print(f"\nFound {len(files)} files:")
                        for f in files:
                            print(f"  - {f.original_name} ({f.size} bytes)")
                            print(f"    Hash: {f.file_hash}")
                    else:
                        print("No files found")
                
                elif command == "download":
                    if not arg:
                        print("Usage: download <file_hash>")
                        continue
                    
                    await client.download_file(arg)
                
                elif command == "quit":
                    break
                
                else:
                    print(f"Unknown command: {command}")
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error: {e}")
    
    finally:
        await client.shutdown()


if __name__ == "__main__":
    asyncio.run(interactive_client())
