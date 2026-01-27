import asyncio
import content_hash_storage
from kademlia_node import KademliaNode

async def test_content_hash():
    # Start 3 nodes
    node1 = KademliaNode('127.0.0.1', 8000)
    node2 = KademliaNode('127.0.0.1', 8001)
    node3 = KademliaNode('127.0.0.1', 8002)
    
    await node1.start()
    await node2.start()
    await node3.start()
    
    # Bootstrap nodes 2 and 3 to node 1
    await node2.bootstrap([('127.0.0.1', 8000)])
    await node3.bootstrap([('127.0.0.1', 8000)])
    
    print("\n=== Network Started ===")
    print(f"Node 1 ID: {node1.local_node.id_hex[:16]}...")
    print(f"Node 2 ID: {node2.local_node.id_hex[:16]}...")
    print(f"Node 3 ID: {node3.local_node.id_hex[:16]}...")
    
    # Store content by hash
    content = {"message": "Hello from P2P!", "sensor": 42.5}
    content_hash = await node1.put_content(content)
    
    print(f"\n=== Content Stored ===")
    print(f"Content: {content}")
    print(f"Hash: {content_hash}")
    
    # Show distribution
    node1.show_content_distribution(content_hash)
    
    # Retrieve from another node
    print("\n=== Retrieving from Node 2 ===")
    retrieved = await node2.get_content(content_hash)
    print(f"Retrieved: {retrieved}")
    
    # Verify integrity
    print(f"\n=== Verification ===")
    is_valid = content_hash_storage.verify_content(retrieved, bytes.fromhex(content_hash))
    print(f"Content integrity: {'✓ VALID' if is_valid else '✗ INVALID'}")
    
    # Cleanup
    await node1.stop()
    await node2.stop()
    await node3.stop()

if __name__ == "__main__":
    asyncio.run(test_content_hash())