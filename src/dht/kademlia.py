"""
Kademlia DHT Node Implementation

High-level interface for a node in the Kademlia DHT network.
Provides methods for bootstrapping, storing, and retrieving values.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from .node import Node, generate_node_id, xor_distance
from .routing_table import RoutingTable, K
from .network import create_protocol, KademliaProtocol
from .rpc import RPCHandler, RPCType, create_rpc_request


logger = logging.getLogger(__name__)


# Kademlia parameters
ALPHA = 3  # Number of parallel lookups
REPUBLISH_INTERVAL = 3600  # Republish values every hour


class KademliaNode:
    """
    A full node in the Kademlia DHT network.
    
    This is the main entry point for using the DHT.
    
    Example:
        node = KademliaNode('127.0.0.1', 8000)
        await node.start()
        await node.bootstrap([('127.0.0.1', 8001)])
        await node.set('my-key', 'my-value')
        value = await node.get('my-key')
        await node.stop()
    """
    
    def __init__(
        self, 
        ip: str, 
        port: int, 
        node_id: Optional[bytes] = None,
        k: int = K,
        alpha: int = ALPHA
    ):
        """
        Initialize a Kademlia node.
        
        Args:
            ip: IP address to bind to
            port: UDP port to listen on
            node_id: Optional 160-bit node ID (generated if not provided)
            k: Bucket size / replication factor
            alpha: Number of parallel lookups
        """
        if node_id is None:
            node_id = generate_node_id()
        
        self.local_node = Node(node_id=node_id, ip=ip, port=port)
        self.k = k
        self.alpha = alpha
        
        # Core components
        self.routing_table = RoutingTable(self.local_node, k=k)
        self.storage: Dict[str, Any] = {}  # Local key-value store
        
        # Network components
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.protocol: Optional[KademliaProtocol] = None
        
        # RPC handler
        self.rpc_handler = RPCHandler(self.routing_table, self.storage)
        
        self._running = False
    
    async def start(self):
        """Start the node and begin listening for messages."""
        if self._running:
            return
        
        self.transport, self.protocol = await create_protocol(
            self.local_node,
            self.rpc_handler.handle_request
        )
        
        self._running = True
        logger.info(f"Kademlia node started: {self.local_node}")
    
    async def stop(self):
        """Stop the node and close the network connection."""
        if not self._running:
            return
        
        self._running = False
        if self.transport:
            self.transport.close()
        
        logger.info(f"Kademlia node stopped: {self.local_node}")
    
    async def bootstrap(self, known_nodes: List[tuple]) -> bool:
        """
        Join the network by connecting to known nodes.
        
        Args:
            known_nodes: List of (ip, port) tuples of known nodes
        
        Returns:
            True if successfully joined the network
        """
        if not known_nodes:
            logger.warning("No bootstrap nodes provided")
            return False
        
        # Ping all known nodes and add responsive ones to routing table
        bootstrap_succeeded = False
        
        for ip, port in known_nodes:
            # Create a temporary node (we don't know its ID yet)
            # We'll learn the real ID from the ping response
            temp_node = Node(
                node_id=generate_node_id(f"{ip}:{port}"),
                ip=ip,
                port=port
            )
            
            response = await self._ping(temp_node)
            if response:
                # Got a response - extract real node info
                sender_data = response.get('sender', {})
                real_node = Node.from_dict(sender_data)
                self.routing_table.add_node(real_node)
                bootstrap_succeeded = True
                logger.info(f"Bootstrap: connected to {real_node}")
        
        if not bootstrap_succeeded:
            logger.warning("Failed to connect to any bootstrap nodes")
            return False
        
        # Perform a lookup for our own ID to populate routing table
        await self.iterative_find_node(self.local_node.node_id)
        
        logger.info(f"Bootstrap complete. Routing table: {self.routing_table}")
        return True
    
    async def set(self, key: str, value: Any) -> bool:
        """
        Store a value in the DHT.
        
        The value is stored on the k nodes closest to the key hash.
        
        Args:
            key: Key to store (will be hashed)
            value: Value to store (must be JSON-serializable)
        
        Returns:
            True if stored on at least one node
        """
        # Hash the key to get target ID
        key_hash = generate_node_id(key)
        key_hex = key_hash.hex()
        
        # Find the k closest nodes to the key
        closest_nodes = await self.iterative_find_node(key_hash)
        
        if not closest_nodes:
            # No nodes found - store locally only
            self.storage[key_hex] = {'value': value, 'stored_by': self.local_node.to_dict()}
            logger.warning(f"No nodes found for key, stored locally only")
            return True
        
        # Store on all closest nodes
        stored_count = 0
        for node in closest_nodes[:self.k]:
            success = await self._store(node, key_hex, value)
            if success:
                stored_count += 1
        
        # Also store locally if we're one of the closest
        local_distance = xor_distance(self.local_node.node_id, key_hash)
        if not closest_nodes or local_distance <= xor_distance(closest_nodes[-1].node_id, key_hash):
            self.storage[key_hex] = {'value': value, 'stored_by': self.local_node.to_dict()}
            stored_count += 1
        
        logger.info(f"Stored key on {stored_count} nodes")
        return stored_count > 0
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the DHT.
        
        Args:
            key: Key to lookup (will be hashed)
        
        Returns:
            The value if found, None otherwise
        """
        key_hash = generate_node_id(key)
        key_hex = key_hash.hex()
        
        # Check local storage first
        if key_hex in self.storage:
            return self.storage[key_hex]['value']
        
        # Perform iterative find value
        result = await self.iterative_find_value(key_hash)
        return result
    
    async def iterative_find_node(self, target_id: bytes) -> List[Node]:
        """
        Perform iterative node lookup.
        
        This is the core Kademlia algorithm:
        1. Start with k closest nodes from routing table
        2. Query alpha nodes in parallel
        3. Add newly discovered nodes
        4. Repeat until no closer nodes are found
        
        Args:
            target_id: 160-bit target ID to find
        
        Returns:
            List of k closest nodes to the target
        """
        # Start with closest nodes from our routing table
        closest = self.routing_table.get_closest_nodes(target_id, count=self.k)
        
        if not closest:
            return []
        
        # Track queried nodes and their distances
        queried: Set[bytes] = set()
        found_nodes: Dict[bytes, Node] = {n.node_id: n for n in closest}
        
        while True:
            # Get unqueried nodes sorted by distance
            unqueried = [
                n for n in found_nodes.values()
                if n.node_id not in queried
            ]
            unqueried.sort(key=lambda n: xor_distance(n.node_id, target_id))
            
            if not unqueried:
                break
            
            # Query alpha closest unqueried nodes
            to_query = unqueried[:self.alpha]
            
            # Parallel queries
            tasks = [
                self._find_node(node, target_id.hex())
                for node in to_query
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Mark as queried
            for node in to_query:
                queried.add(node.node_id)
            
            # Process results
            new_nodes_found = False
            for result in results:
                if isinstance(result, Exception) or result is None:
                    continue
                
                for node in result:
                    if node.node_id not in found_nodes and node.node_id != self.local_node.node_id:
                        found_nodes[node.node_id] = node
                        self.routing_table.add_node(node)
                        new_nodes_found = True
            
            # If no new closer nodes, we're done
            if not new_nodes_found:
                break
        
        # Return k closest
        all_nodes = list(found_nodes.values())
        all_nodes.sort(key=lambda n: xor_distance(n.node_id, target_id))
        return all_nodes[:self.k]
    
    async def iterative_find_value(self, key_hash: bytes) -> Optional[Any]:
        """
        Perform iterative value lookup.
        
        Similar to find_node, but returns immediately if value is found.
        
        Args:
            key_hash: 160-bit hash of the key
        
        Returns:
            The value if found, None otherwise
        """
        key_hex = key_hash.hex()
        
        # Start with closest nodes
        closest = self.routing_table.get_closest_nodes(key_hash, count=self.k)
        
        if not closest:
            return None
        
        queried: Set[bytes] = set()
        found_nodes: Dict[bytes, Node] = {n.node_id: n for n in closest}
        
        while True:
            unqueried = [
                n for n in found_nodes.values()
                if n.node_id not in queried
            ]
            unqueried.sort(key=lambda n: xor_distance(n.node_id, key_hash))
            
            if not unqueried:
                break
            
            to_query = unqueried[:self.alpha]
            
            for node in to_query:
                queried.add(node.node_id)
                
                result = await self._find_value(node, key_hex)
                if result is None:
                    continue
                
                # Check if we got the value
                if result.get('found'):
                    value = result.get('value')
                    # Cache locally
                    self.storage[key_hex] = {'value': value, 'stored_by': node.to_dict()}
                    return value
                
                # Otherwise, add returned nodes
                for node_data in result.get('nodes', []):
                    new_node = Node.from_dict(node_data)
                    if new_node.node_id not in found_nodes and new_node.node_id != self.local_node.node_id:
                        found_nodes[new_node.node_id] = new_node
                        self.routing_table.add_node(new_node)
        
        return None
    
    # ========== Low-level RPC methods ==========
    
    async def _ping(self, node: Node) -> Optional[dict]:
        """Send PING RPC to a node."""
        if not self.protocol:
            return None
        
        payload = create_rpc_request(RPCType.PING)
        response = await self.protocol.send_request(node, RPCType.PING.value, payload)
        
        if response and response.get('payload', {}).get('status') == 'PONG':
            # Update routing table
            sender_data = response.get('sender', {})
            real_node = Node.from_dict(sender_data)
            self.routing_table.add_node(real_node)
            return response
        
        return None
    
    async def _store(self, node: Node, key: str, value: Any) -> bool:
        """Send STORE RPC to a node."""
        if not self.protocol:
            return False
        
        payload = create_rpc_request(RPCType.STORE, key=key, value=value)
        response = await self.protocol.send_request(node, RPCType.STORE.value, payload)
        
        return response is not None and response.get('payload', {}).get('status') == 'stored'
    
    async def _find_node(self, node: Node, target_hex: str) -> Optional[List[Node]]:
        """Send FIND_NODE RPC to a node."""
        if not self.protocol:
            return None
        
        payload = create_rpc_request(RPCType.FIND_NODE, target=target_hex)
        response = await self.protocol.send_request(node, RPCType.FIND_NODE.value, payload)
        
        if response is None:
            return None
        
        payload_data = response.get('payload', {})
        nodes_data = payload_data.get('nodes', [])
        
        return [Node.from_dict(n) for n in nodes_data]
    
    async def _find_value(self, node: Node, key: str) -> Optional[dict]:
        """Send FIND_VALUE RPC to a node."""
        if not self.protocol:
            return None
        
        payload = create_rpc_request(RPCType.FIND_VALUE, key=key)
        response = await self.protocol.send_request(node, RPCType.FIND_VALUE.value, payload)
        
        if response is None:
            return None
        
        return response.get('payload', {})
    
    def debug_status(self) -> str:
        """Return debug information about the node."""
        lines = [
            f"=== Kademlia Node: {self.local_node} ===",
            f"Running: {self._running}",
            f"Routing table: {self.routing_table.total_nodes()} nodes",
            f"Local storage: {len(self.storage)} keys",
        ]
        return "\n".join(lines)
