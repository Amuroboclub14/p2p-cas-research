#!/usr/bin/env python3
"""
DHT-Enabled P2P Node

Runs a Kademlia DHT node alongside the CAS storage.
When files are stored, chunk locations are registered in the DHT.
DHT state is persisted to disk so it survives restarts.
"""

import asyncio
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.dht.kademlia import KademliaNode
from src.dht.node import generate_node_id
from src.cas import cas


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Persistence file for DHT storage
DHT_STORAGE_FILE = "storage/dht_storage.json"


def load_dht_storage() -> dict:
    """Load persisted DHT storage from disk."""
    if os.path.exists(DHT_STORAGE_FILE):
        try:
            with open(DHT_STORAGE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load DHT storage: {e}")
    return {}


def save_dht_storage(storage: dict):
    """Save DHT storage to disk."""
    os.makedirs(os.path.dirname(DHT_STORAGE_FILE), exist_ok=True)
    try:
        with open(DHT_STORAGE_FILE, 'w') as f:
            json.dump(storage, f, indent=2)
        logger.info(f"DHT storage saved ({len(storage)} entries)")
    except IOError as e:
        logger.error(f"Could not save DHT storage: {e}")


class DHTEnabledNode:
    """
    A P2P node with both DHT and CAS functionality.
    
    When files are stored in CAS, chunk locations are published to DHT.
    DHT storage is persisted to disk.
    """
    
    def __init__(self, ip: str, port: int, storage_dir: str = "storage/hashed_files"):
        self.ip = ip
        self.port = port
        self.storage_dir = storage_dir
        self.dht_node = KademliaNode(ip, port)
        self._running = False
    
    async def start(self):
        """Start the DHT node and load persisted storage."""
        await self.dht_node.start()
        
        # Load persisted DHT storage
        persisted = load_dht_storage()
        if persisted:
            self.dht_node.storage = persisted
            print(f"   Loaded {len(persisted)} entries from disk")
        
        self._running = True
        print(f"\n✅ DHT Node started: {self.dht_node.local_node}")
        print(f"   Node ID: {self.dht_node.local_node.id_hex}")
    
    async def stop(self):
        """Stop the DHT node and save storage to disk."""
        # Save DHT storage before stopping
        save_dht_storage(self.dht_node.storage)
        
        await self.dht_node.stop()
        self._running = False
        print("DHT Node stopped")
    
    async def bootstrap(self, nodes: list):
        """Connect to other nodes in the network."""
        if await self.dht_node.bootstrap(nodes):
            print(f"✅ Connected to network ({self.dht_node.routing_table.total_nodes()} peers)")
        else:
            print("⚠️  No peers connected (standalone mode)")
    
    async def store_file(self, filepath: str) -> str:
        """
        Store a file in CAS and register chunks in DHT.
        
        Returns the file hash.
        """
        print(f"\n📁 Storing file: {filepath}")
        
        # Use existing CAS to store the file
        file_hash = cas.store_file(filepath, self.storage_dir)
        print(f"   File hash: {file_hash}")
        
        # Load index to get chunk info
        index = cas.load_index(self.storage_dir)
        file_meta = index.get(file_hash, {})
        # CAS stores chunks under 'data_chunks' and 'parity_chunks' keys
        chunks = file_meta.get('data_chunks', []) + file_meta.get('parity_chunks', [])
        
        # Register each chunk in DHT
        print(f"   Registering {len(chunks)} chunks in DHT...")
        for chunk_hash in chunks:
            await self.dht_node.set(
                chunk_hash, 
                {
                    'holder': self.dht_node.local_node.to_dict(),
                    'file_hash': file_hash,
                    'storage_dir': self.storage_dir
                }
            )
        
        print(f"✅ File stored and chunks registered in DHT")
        return file_hash
    
    async def lookup_chunk(self, chunk_hash: str):
        """Find which node has a specific chunk."""
        result = await self.dht_node.get(chunk_hash)
        return result
    
    def show_dht_state(self):
        """Print the current DHT state."""
        print("\n" + "="*60)
        print("                    DHT STATE")
        print("="*60)
        
        # Local node info
        print(f"\n📍 Local Node: {self.dht_node.local_node}")
        print(f"   Full ID: {self.dht_node.local_node.id_hex}")
        
        # Routing table
        rt = self.dht_node.routing_table
        print(f"\n📋 Routing Table: {rt.total_nodes()} known peers")
        
        if rt.total_nodes() > 0:
            for i, bucket in enumerate(rt.buckets):
                if len(bucket) > 0:
                    print(f"   Bucket {i}: {len(bucket)} nodes")
                    for node in bucket.get_nodes():
                        print(f"      - {node}")
        
        # Local storage (DHT values we hold)
        storage = self.dht_node.storage
        print(f"\n💾 Local DHT Storage: {len(storage)} entries")
        
        if storage:
            for key, data in list(storage.items())[:10]:  # Show max 10
                short_key = key[:16] + "..."
                value = data.get('value', {})
                if isinstance(value, dict) and 'holder' in value:
                    print(f"   {short_key} → chunk held by {value['holder'].get('ip')}:{value['holder'].get('port')}")
                else:
                    print(f"   {short_key} → {str(value)[:50]}")
            
            if len(storage) > 10:
                print(f"   ... and {len(storage) - 10} more entries")
        
        print("\n" + "="*60)
    
    def show_local_files(self):
        """Show files stored locally in CAS."""
        print("\n📁 Local CAS Files:")
        cas.list_files(self.storage_dir)


async def interactive_mode(node: DHTEnabledNode):
    """Run an interactive CLI for the DHT node."""
    print("\n" + "="*60)
    print("        DHT-ENABLED P2P NODE - INTERACTIVE MODE")
    print("="*60)
    print("\nCommands:")
    print("  store <filepath>     - Store a file and register in DHT")
    print("  lookup <chunk_hash>  - Find who has a chunk")
    print("  dht                  - Show DHT state (routing table + storage)")
    print("  files                - Show local CAS files")
    print("  peers                - Show known peers")
    print("  quit                 - Exit")
    print("="*60 + "\n")
    
    while True:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("dht> ").strip()
            )
            
            if not cmd:
                continue
            
            parts = cmd.split(maxsplit=1)
            action = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else None
            
            if action == "quit" or action == "exit":
                break
            
            elif action == "store":
                if not arg:
                    print("Usage: store <filepath>")
                    continue
                if not os.path.exists(arg):
                    print(f"File not found: {arg}")
                    continue
                await node.store_file(arg)
            
            elif action == "lookup":
                if not arg:
                    print("Usage: lookup <chunk_hash>")
                    continue
                result = await node.lookup_chunk(arg)
                if result:
                    print(f"Found: {json.dumps(result, indent=2)}")
                else:
                    print("Chunk not found in DHT")
            
            elif action == "dht":
                node.show_dht_state()
            
            elif action == "files":
                node.show_local_files()
            
            elif action == "peers":
                peers = node.dht_node.routing_table.get_all_nodes()
                print(f"\nKnown peers: {len(peers)}")
                for p in peers:
                    print(f"  - {p}")
            
            else:
                print(f"Unknown command: {action}")
        
        except KeyboardInterrupt:
            print("\n")
            break
        except Exception as e:
            print(f"Error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="DHT-Enabled P2P Node")
    parser.add_argument("--port", type=int, default=8001, help="UDP port for DHT (default: 8001)")
    parser.add_argument("--ip", default="127.0.0.1", help="IP address (default: 127.0.0.1)")
    parser.add_argument("--bootstrap", help="Bootstrap node (ip:port)")
    parser.add_argument("--storage", default="storage/hashed_files", help="CAS storage directory")
    
    args = parser.parse_args()
    
    # Create and start node
    node = DHTEnabledNode(args.ip, args.port, args.storage)
    await node.start()
    
    # Bootstrap if specified
    if args.bootstrap:
        try:
            host, port = args.bootstrap.split(":")
            await node.bootstrap([(host, int(port))])
        except ValueError:
            print(f"Invalid bootstrap address: {args.bootstrap}")
    
    # Run interactive mode
    try:
        await interactive_mode(node)
    finally:
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
