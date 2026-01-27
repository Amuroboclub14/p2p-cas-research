import hashlib
import json
from typing import Any, Optional, List
import logging
from typing import Any, Dict, List, Optional, Set

from .node import Node, generate_node_id, xor_distance
from .routing_table import RoutingTable, K
from .network import create_protocol, KademliaProtocol
from .rpc import RPCHandler, RPCType, create_rpc_request
logger = logging.getLogger(__name__) 


class ContentHashStorage:
  
    @staticmethod
    def hash_content(content: Any) -> bytes:
        """
        Generate a 160-bit SHA-1 hash of content.
        
        Args:
            content: Any JSON-serializable data or bytes
        
        Returns:
            160-bit (20-byte) content hash
        """
        if isinstance(content, bytes):
            return hashlib.sha1(content).digest()
        elif isinstance(content, str):
            return hashlib.sha1(content.encode('utf-8')).digest()
        else:
            # For complex objects, serialize to JSON first
            json_str = json.dumps(content, sort_keys=True)
            return hashlib.sha1(json_str.encode('utf-8')).digest()
    
    @staticmethod
    def verify_content(content: Any, expected_hash: bytes) -> bool:
        """
        Verify that content matches its hash.
        """
        actual_hash = ContentHashStorage.hash_content(content)
        return actual_hash == expected_hash


# Add these methods to your KademliaNode class:

async def put_content(self, content: Any) -> str:
    """
    Store content in the DHT using content-based addressing.
    
    Example:
        content_hash = await node.put_content(b"Hello, P2P world!")
        # Later retrieve with:
        retrieved = await node.get_content(content_hash)
    """
    # Hash the content
    content_hash = ContentHashStorage.hash_content(content)
    content_hash_hex = content_hash.hex()
    
    # Find k closest nodes to the content hash
    closest_nodes = await self.iterative_find_node(content_hash)
    
    if not closest_nodes:
        # No other nodes - store locally only
        self.storage[content_hash_hex] = {
            'content': content,
            'hash': content_hash_hex,
            'stored_by': self.local_node.to_dict(),
            'is_content_addressed': True
        }
        logger.info(f"Content stored locally: {content_hash_hex[:16]}...")
        return content_hash_hex
    
    # Store on k closest nodes
    stored_count = 0
    for node in closest_nodes[:self.k]:
        success = await self._store(node, content_hash_hex, {
            'content': content,
            'hash': content_hash_hex,
            'is_content_addressed': True
        })
        if success:
            stored_count += 1
    
    # Also store locally if we're one of the closest
    local_distance = xor_distance(self.local_node.node_id, content_hash)
    if not closest_nodes or local_distance <= xor_distance(closest_nodes[-1].node_id, content_hash):
        self.storage[content_hash_hex] = {
            'content': content,
            'hash': content_hash_hex,
            'stored_by': self.local_node.to_dict(),
            'is_content_addressed': True
        }
        stored_count += 1
    
    logger.info(f"Content stored on {stored_count} nodes with hash: {content_hash_hex[:16]}...")
    return content_hash_hex


async def get_content(self, content_hash_hex: str) -> Optional[Any]:
    """
    Retrieve content from the DHT by its hash.
        
    Example:
        content = await node.get_content("a94a8fe5ccb19ba61c4c0873d391e987982fbbd3")
    """
    content_hash = bytes.fromhex(content_hash_hex)
    
    # Check local storage first
    if content_hash_hex in self.storage:
        stored_data = self.storage[content_hash_hex]
        content = stored_data.get('content')
        
        # Verify content integrity
        if stored_data.get('is_content_addressed'):
            if ContentHashStorage.verify_content(content, content_hash):
                return content
            else:
                logger.error(f"Content hash mismatch for {content_hash_hex[:16]}!")
                # Data corrupted - delete it
                del self.storage[content_hash_hex]
    
    # Search the network
    result = await self.iterative_find_value(content_hash)
    
    if result is None:
        return None
    
    # Verify retrieved content matches its hash
    if isinstance(result, dict) and 'content' in result:
        content = result['content']
    else:
        content = result
    
    if ContentHashStorage.verify_content(content, content_hash):
        # Cache locally
        self.storage[content_hash_hex] = {
            'content': content,
            'hash': content_hash_hex,
            'is_content_addressed': True
        }
        return content
    else:
        logger.error(f"Retrieved content doesn't match hash {content_hash_hex[:16]}!")
        return None


async def put_file(self, file_path: str) -> str:
    """
    Store a file in the DHT by its content hash.
    Example:
        file_hash = await node.put_file("my_robot_config.json")
        print(f"File stored with hash: {file_hash}")
    """
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return await self.put_content(content)


async def get_file(self, content_hash_hex: str, output_path: str) -> bool:
    """
    Retrieve a file from the DHT and save it.
    
    Example:
        success = await node.get_file(file_hash, "downloaded_config.json")
    """
    content = await self.get_content(content_hash_hex)
    
    if content is None:
        return False
    
    if not isinstance(content, bytes):
        # Convert to bytes if needed
        if isinstance(content, str):
            content = content.encode('utf-8')
        else:
            content = json.dumps(content).encode('utf-8')
    
    with open(output_path, 'wb') as f:
        f.write(content)
    
    return True


def show_content_distribution(self, content_hash_hex: str):
    """
    Show which nodes are responsible for storing a piece of content.
    
    Args:
        content_hash_hex: Hash of the content to analyze
    """
    content_hash = bytes.fromhex(content_hash_hex)
    
    # Get all nodes we know about
    all_nodes = self.routing_table.get_all_nodes()
    
    # Calculate distances
    node_distances = []
    for node in all_nodes:
        distance = xor_distance(node.node_id, content_hash)
        node_distances.append((node, distance))
    
    # Add ourselves
    local_distance = xor_distance(self.local_node.node_id, content_hash)
    node_distances.append((self.local_node, local_distance))
    
    # Sort by distance
    node_distances.sort(key=lambda x: x[1])
    
    print(f"\n=== Content Distribution for {content_hash_hex[:16]}... ===")
    print(f"Content hash: {content_hash_hex}")
    print(f"\nClosest {self.k} nodes (responsible for storing):")
    
    for i, (node, distance) in enumerate(node_distances[:self.k]):
        is_local = node.node_id == self.local_node.node_id
        marker = "★ LOCAL" if is_local else ""
        print(f"  {i+1}. {node} - distance: {distance} {marker}")
    
    if len(node_distances) > self.k:
        print(f"\n... and {len(node_distances) - self.k} other nodes farther away")
    
    print("=" * 60)


# Example usage demonstration:
"""
# In your main.py or test script:

async def demo_content_hash_storage():
    # Create a node
    node = KademliaNode('127.0.0.1', 8000)
    await node.start()
    
    # Bootstrap to network
    await node.bootstrap([('127.0.0.1', 8001), ('127.0.0.1', 8002)])
    
    # Store content by hash
    content = {"sensor_data": [1.2, 3.4, 5.6], "timestamp": "2024-01-26"}
    content_hash = await node.put_content(content)
    print(f"Stored content with hash: {content_hash}")
    
    # Show where it's stored
    node.show_content_distribution(content_hash)
    
    # Retrieve content
    retrieved = await node.get_content(content_hash)
    print(f"Retrieved: {retrieved}")
    
    # Store a file
    file_hash = await node.put_file("robot_config.json")
    print(f"File hash: {file_hash}")
    
    # Later, download the file
    await node.get_file(file_hash, "downloaded_config.json")
    
    await node.stop()

# Run it
asyncio.run(demo_content_hash_storage())
"""