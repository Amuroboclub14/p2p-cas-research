#!/usr/bin/env python3
"""
Universal P2P Node Runner

Run any node by passing a node number:
    python run_node.py 1    # Start Node1 on port 9000, DHT 8468
    python run_node.py 2    # Start Node2 on port 9001, DHT 8469
    python run_node.py 3    # Start Node3 on port 9002, DHT 8470
    
Ports are auto-assigned: 9000 + (node_num - 1)
DHT ports are auto-assigned: 8468 + (node_num - 1)
"""

import asyncio
import sys
import logging
from src.network.p2p_node import P2PNode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def run_node(node_name: str, port: int, dht_port: int):
    """
    Start a P2P node.
    
    Args:
        node_name: Name of the node (e.g., 'Node1')
        port: TCP port for serving chunks
        dht_port: UDP port for DHT
    """
    try:
        node = P2PNode(
            node_id=node_name,
            server_host='127.0.0.1',
            server_port=port,
            dht_port=dht_port,
            storage_dir='storage/hashed_files'
        )
        
        print(f"\n{'='*60}")
        print(f"Starting {node_name}")
        print(f"  Server: 127.0.0.1:{port}")
        print(f"  DHT:    127.0.0.1:{dht_port}")
        print(f"{'='*60}\n")
        
        # Initialize node
        await node.initialize()
        
        # Start server
        node.start_server()
        
        print(f"[{node_name}] ✓ Node ready")
        print(f"[{node_name}] Press Ctrl+C to stop\n")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        print(f"\n[{node_name}] Shutting down...")
        if 'node' in locals():
            await node.shutdown()
        print(f"[{node_name}] Shutdown complete")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


def main():
    """Parse arguments and start node"""
    
    if len(sys.argv) < 2:
        print("Usage: python run_node.py <node_number>\n")
        print("Examples:")
        print("  python run_node.py 1    # Node1 on port 9000")
        print("  python run_node.py 2    # Node2 on port 9001")
        print("  python run_node.py 3    # Node3 on port 9002")
        print("  python run_node.py 10   # Node10 on port 9009")
        sys.exit(1)
    
    try:
        node_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: Node number must be an integer, got '{sys.argv[1]}'")
        sys.exit(1)
    
    if node_num < 1:
        print("Error: Node number must be >= 1")
        sys.exit(1)
    
    # Auto-assign ports
    node_name = f"Node{node_num}"
    port = 9000 + (node_num - 1)
    dht_port = 8468 + (node_num - 1)
    
    # Run node
    asyncio.run(run_node(node_name, port, dht_port))


if __name__ == "__main__":
    main()
