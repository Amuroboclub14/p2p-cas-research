"""
Kademlia RPC Handlers

Defines the four core Kademlia RPCs:
- PING: Check if node is alive
- STORE: Store a key-value pair
- FIND_NODE: Find k closest nodes to a target ID
- FIND_VALUE: Find value for key, or k closest nodes
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from .node import Node
from .routing_table import RoutingTable, K


class RPCType(Enum):
    """Kademlia RPC types."""
    PING = "PING"
    STORE = "STORE"
    FIND_NODE = "FIND_NODE"
    FIND_VALUE = "FIND_VALUE"


class RPCHandler:
    """
    Handles incoming Kademlia RPC requests.
    
    This class processes requests and generates appropriate responses.
    """
    
    def __init__(self, routing_table: RoutingTable, storage: Dict[str, Any]):
        """
        Args:
            routing_table: The node's routing table
            storage: Dictionary for key-value storage
        """
        self.routing_table = routing_table
        self.storage = storage
    
    async def handle_request(
        self, 
        rpc: str, 
        sender: Node, 
        payload: dict,
        addr: tuple
    ) -> dict:
        """
        Process an incoming RPC request.
        
        Args:
            rpc: RPC type string
            sender: The node that sent the request
            payload: Request payload
            addr: Source address (ip, port)
        
        Returns:
            Response payload dict
        """
        # Update routing table with sender (they're alive!)
        self.routing_table.add_node(sender)
        
        # Route to appropriate handler
        if rpc == RPCType.PING.value:
            return self._handle_ping(sender, payload)
        elif rpc == RPCType.STORE.value:
            return self._handle_store(sender, payload)
        elif rpc == RPCType.FIND_NODE.value:
            return self._handle_find_node(sender, payload)
        elif rpc == RPCType.FIND_VALUE.value:
            return self._handle_find_value(sender, payload)
        else:
            return {"error": f"Unknown RPC: {rpc}"}
    
    def _handle_ping(self, sender: Node, payload: dict) -> dict:
        """
        Handle PING request.
        
        Simply returns PONG to confirm we're alive.
        """
        return {"status": "PONG"}
    
    def _handle_store(self, sender: Node, payload: dict) -> dict:
        """
        Handle STORE request.
        
        Store the key-value pair in local storage.
        
        Expected payload:
            key: hex string of the key
            value: the value to store
        """
        key = payload.get('key')
        value = payload.get('value')
        
        if not key:
            return {"status": "error", "message": "Missing key"}
        
        self.storage[key] = {
            'value': value,
            'stored_by': sender.to_dict(),
        }
        
        return {"status": "stored"}
    
    def _handle_find_node(self, sender: Node, payload: dict) -> dict:
        """
        Handle FIND_NODE request.
        
        Return the k closest nodes to the target ID.
        
        Expected payload:
            target: hex string of target node ID
        """
        target_hex = payload.get('target')
        if not target_hex:
            return {"error": "Missing target"}
        
        try:
            target_id = bytes.fromhex(target_hex)
        except ValueError:
            return {"error": "Invalid target ID"}
        
        # Get k closest nodes
        closest = self.routing_table.get_closest_nodes(target_id, count=K)
        
        # Don't include the requester in the response
        closest = [n for n in closest if n.node_id != sender.node_id]
        
        return {
            "nodes": [node.to_dict() for node in closest]
        }
    
    def _handle_find_value(self, sender: Node, payload: dict) -> dict:
        """
        Handle FIND_VALUE request.
        
        If we have the value, return it.
        Otherwise, return the k closest nodes (like FIND_NODE).
        
        Expected payload:
            key: hex string of the key to find
        """
        key = payload.get('key')
        if not key:
            return {"error": "Missing key"}
        
        # Check if we have the value
        if key in self.storage:
            return {
                "found": True,
                "value": self.storage[key]['value']
            }
        
        # We don't have it - return closest nodes
        try:
            target_id = bytes.fromhex(key)
        except ValueError:
            return {"error": "Invalid key format"}
        
        closest = self.routing_table.get_closest_nodes(target_id, count=K)
        closest = [n for n in closest if n.node_id != sender.node_id]
        
        return {
            "found": False,
            "nodes": [node.to_dict() for node in closest]
        }


def create_rpc_request(rpc_type: RPCType, **kwargs) -> dict:
    """
    Create an RPC request payload.
    
    Helper function to create properly formatted request payloads.
    """
    if rpc_type == RPCType.PING:
        return {}
    
    elif rpc_type == RPCType.STORE:
        return {
            'key': kwargs.get('key'),
            'value': kwargs.get('value')
        }
    
    elif rpc_type == RPCType.FIND_NODE:
        return {
            'target': kwargs.get('target')
        }
    
    elif rpc_type == RPCType.FIND_VALUE:
        return {
            'key': kwargs.get('key')
        }
    
    return {}
