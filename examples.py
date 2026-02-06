#!/usr/bin/env python3
"""
Example: Running a P2P Network with Multiple Nodes

This script demonstrates how to set up and run a P2P file sharing network
with multiple nodes on your local machine.
"""

import asyncio
import sys
import os
import logging
from src.dht.kademlia import KademliaNode
from src.network.p2p_node import P2PNode
from src.cas.cas import store_file

logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def run_node(node_id: str, server_port: int, dht_port: int, bootstrap_port: int):
    """
    Run a single P2P node.
    
    Args:
        node_id: Unique node identifier
        server_port: TCP port for serving chunks
        dht_port: UDP port for DHT
        bootstrap_port: Port to bootstrap DHT from (0 = this node)
    """
    
    storage_dir = f"storage/hashed_files"
    
    node = P2PNode(
        node_id=node_id,
        server_host="127.0.0.1",
        server_port=server_port,
        dht_port=dht_port,
        storage_dir=storage_dir
    )
    
    print(f"\n{'='*60}")
    print(f"Starting {node_id}")
    print(f"  Server: 127.0.0.1:{server_port}")
    print(f"  DHT:    127.0.0.1:{dht_port}")
    print(f"{'='*60}\n")
    
    try:
        # Initialize node
        await node.initialize()
        
        # Start server
        node.start_server()
        
        # If this is not the first node, bootstrap to another node
        if bootstrap_port > 0:
            print(f"[{node_id}] Bootstrapping to localhost:{bootstrap_port}...")
            try:
                await node.dht_node.bootstrap([("127.0.0.1", bootstrap_port)])
            except Exception as e:
                logger.warning(f"[{node_id}] Bootstrap warning: {e}")
        
        # Keep node running
        print(f"[{node_id}] Node ready. Press Ctrl+C to stop.\n")
        while True:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        print(f"\n[{node_id}] Shutdown signal received...")
        await node.shutdown()


async def run_network_demo():
    """
    Demo: Run 3 nodes and upload a file to one, then download from another.
    """
    
    print("""
    ╔════════════════════════════════════════════════╗
    ║    P2P File Sharing Network Demo               ║
    ║                                                 ║
    ║  This demo:                                    ║
    ║  1. Starts 3 P2P nodes                         ║
    ║  2. Stores a file on Node1                     ║
    ║  3. Downloads it from Node3 (via peers)        ║
    ╚════════════════════════════════════════════════╝
    """)
    
    # Start nodes concurrently
    node1 = asyncio.create_task(run_node("Node1", 9000, 8468, 0))
    await asyncio.sleep(1)  # Let first node start
    
    node2 = asyncio.create_task(run_node("Node2", 9001, 8469, 8468))
    await asyncio.sleep(1)
    
    node3 = asyncio.create_task(run_node("Node3", 9002, 8470, 8468))
    
    # Wait for all nodes
    await asyncio.gather(node1, node2, node3)


def example_store_file():
    """
    Example: Store a file using the CAS system.
    
    This demonstrates how to:
    1. Store a file using CAS (Content Addressable Storage)
    2. The file is broken into chunks
    3. Each chunk is hashed and stored
    4. The chunks would be registered in DHT
    """
    
    print("""
    Example: Storing a File
    ═══════════════════════════════════════════════════
    
    Usage from command line:
    
    $ python main.py store path/to/file.txt
    
    This will:
    1. Read file.txt
    2. Split into chunks
    3. Hash each chunk (SHA-256)
    4. Store chunks in storage/hashed_files/
    5. Create metadata in cas_index.json
    
    Then, to publish chunks to P2P network:
    
    from src.network.p2p_node import P2PNode
    
    node = P2PNode(...)
    await node.initialize()
    
    # Register our chunks in DHT
    await node.peer_manager.register_chunks_in_dht(
        node.peer_manager.local_chunks
    )
    ════════════════════════════════════════════════════
    """)


def example_download_file():
    """
    Example: Download a file from the P2P network.
    
    Shows how to use the P2PClient to discover and download files.
    """
    
    print("""
    Example: Downloading a File from Network
    ════════════════════════════════════════════════════
    
    from src.network.p2p_client_new import P2PClient
    
    # Create client
    client = P2PClient(
        dht_bootstrap_nodes=[("127.0.0.1", 8468)],
        download_dir="downloads"
    )
    
    # Initialize
    await client.initialize()
    
    # List available files
    files = await client.list_files()
    for f in files:
        print(f"{f.original_name}: {f.file_hash}")
    
    # Download a file
    file_hash = "abc123..."  # From list above
    success = await client.download_file(file_hash)
    
    if success:
        print(f"✓ Downloaded to downloads/")
    else:
        print("✗ Download failed")
    
    await client.shutdown()
    ════════════════════════════════════════════════════
    """)


def example_integration():
    """
    Example: Full integration example.
    """
    
    print("""
    Complete Integration Example
    ════════════════════════════════════════════════════
    
    Full workflow showing:
    1. Node initialization and startup
    2. File storage
    3. Chunk registration in DHT
    4. File discovery by another client
    5. Parallel chunk download
    
    ─────────────────────────────────────────────────────
    Step 1: Run Node Server
    ─────────────────────────────────────────────────────
    
    import asyncio
    from src.network.p2p_node import P2PNode
    
    async def main():
        node = P2PNode(
            node_id="MyNode",
            server_host="127.0.0.1",
            server_port=9000,
            dht_port=8468,
            storage_dir="storage/hashed_files"
        )
        
        # Initialize and start
        await node.initialize()
        node.start_server()
        
        print("Node running...")
        while True:
            await asyncio.sleep(1)
    
    asyncio.run(main())
    
    ─────────────────────────────────────────────────────
    Step 2: Store Files (in another terminal)
    ─────────────────────────────────────────────────────
    
    $ python main.py store path/to/file.txt
    
    Output:
    File stored with hash: abc123...
    
    Then publish chunks to DHT:
    
    # Connect to node and register chunks
    node.peer_manager.register_chunks_in_dht(chunks)
    
    ─────────────────────────────────────────────────────
    Step 3: Download Files (from another client)
    ─────────────────────────────────────────────────────
    
    from src.network.p2p_client_new import P2PClient
    
    client = P2PClient(
        dht_bootstrap_nodes=[("127.0.0.1", 8468)]
    )
    await client.initialize()
    
    # Download by hash
    await client.download_file("abc123...")
    
    Results:
    - File discovered via DHT
    - Chunks found on various peers
    - Downloaded in parallel
    - Verified and assembled
    
    ════════════════════════════════════════════════════
    """)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "demo":
            print("Starting network demo with 3 nodes...\n")
            try:
                asyncio.run(run_network_demo())
            except KeyboardInterrupt:
                print("\nDemo stopped by user")
        
        elif command == "store":
            example_store_file()
        
        elif command == "download":
            example_download_file()
        
        elif command == "integration":
            example_integration()
        
        else:
            print(f"Unknown command: {command}")
            print("\nUsage:")
            print("  python examples.py demo          # Run 3-node network demo")
            print("  python examples.py store         # Show file storage example")
            print("  python examples.py download      # Show download example")
            print("  python examples.py integration   # Show full integration")
    
    else:
        print("""
        P2P File Sharing Examples
        ═══════════════════════════════════════════════════════
        
        Usage:
            python examples.py <command>
        
        Commands:
            demo           - Run demo with 3 nodes
            store          - Show how to store files
            download       - Show how to download files
            integration    - Show complete integration example
        
        ═══════════════════════════════════════════════════════
        """)
