"""
Kademlia Node Implementation

A Node represents a peer in the Kademlia DHT network.
Each node has a unique 160-bit ID, IP address, and port.
"""

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Optional


# Kademlia constants
ID_BITS = 160  # Size of node IDs in bits
ID_BYTES = ID_BITS // 8  # Size of node IDs in bytes (20)


def generate_node_id(seed: Optional[str] = None) -> bytes:
    """
    Generate a 160-bit node ID.
    
    Args:
        seed: Optional string to seed the ID generation.
              If None, generates a random ID.
    
    Returns:
        A 20-byte (160-bit) node ID.
    """
    if seed is not None:
        return hashlib.sha1(seed.encode()).digest()
    else:
        return hashlib.sha1(os.urandom(32)).digest()


def bytes_to_int(data: bytes) -> int:
    """Convert bytes to integer for XOR operations."""
    return int.from_bytes(data, byteorder='big')


def int_to_bytes(value: int, length: int = ID_BYTES) -> bytes:
    """Convert integer back to bytes."""
    return value.to_bytes(length, byteorder='big')


def xor_distance(id1: bytes, id2: bytes) -> int:
    """
    Calculate XOR distance between two node IDs.
    
    The XOR distance is the fundamental metric in Kademlia.
    Nodes that share more prefix bits are "closer" in the XOR space.
    
    Args:
        id1: First 160-bit node ID
        id2: Second 160-bit node ID
    
    Returns:
        Integer representing the XOR distance
    """
    return bytes_to_int(id1) ^ bytes_to_int(id2)


def get_prefix_length(distance: int) -> int:
    """
    Get the number of shared prefix bits between two IDs.
    
    This determines which k-bucket a node belongs to.
    A distance of 0 means all bits match (same node).
    A large distance means fewer prefix bits match.
    
    Args:
        distance: XOR distance between two nodes
    
    Returns:
        Number of shared prefix bits (0-160)
    """
    if distance == 0:
        return ID_BITS
    return ID_BITS - distance.bit_length()


@dataclass
class Node:
    """
    Represents a node in the Kademlia DHT network.
    
    Attributes:
        node_id: 160-bit unique identifier (20 bytes)
        ip: IP address of the node
        port: UDP port the node listens on
        last_seen: Timestamp of last contact with this node
    """
    node_id: bytes
    ip: str
    port: int
    last_seen: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Validate node ID length."""
        if len(self.node_id) != ID_BYTES:
            raise ValueError(f"Node ID must be {ID_BYTES} bytes, got {len(self.node_id)}")
    
    def distance_to(self, other: 'Node') -> int:
        """Calculate XOR distance to another node."""
        return xor_distance(self.node_id, other.node_id)
    
    def distance_to_id(self, target_id: bytes) -> int:
        """Calculate XOR distance to a target ID."""
        return xor_distance(self.node_id, target_id)
    
    def prefix_length_to(self, other: 'Node') -> int:
        """Get shared prefix length with another node."""
        return get_prefix_length(self.distance_to(other))
    
    def update_last_seen(self):
        """Update the last seen timestamp to now."""
        self.last_seen = time.time()
    
    @property
    def id_hex(self) -> str:
        """Return node ID as hex string for display."""
        return self.node_id.hex()
    
    @property
    def short_id(self) -> str:
        """Return first 8 chars of hex ID for logging."""
        return self.id_hex[:8]
    
    @property
    def address(self) -> tuple:
        """Return (ip, port) tuple."""
        return (self.ip, self.port)
    
    def to_dict(self) -> dict:
        """Serialize node to dictionary for network transport."""
        return {
            'node_id': self.node_id.hex(),
            'ip': self.ip,
            'port': self.port
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Node':
        """Deserialize node from dictionary."""
        return cls(
            node_id=bytes.fromhex(data['node_id']),
            ip=data['ip'],
            port=data['port']
        )
    
    def __eq__(self, other: object) -> bool:
        """Two nodes are equal if they have the same ID."""
        if not isinstance(other, Node):
            return False
        return self.node_id == other.node_id
    
    def __hash__(self) -> int:
        """Hash based on node ID."""
        return hash(self.node_id)
    
    def __repr__(self) -> str:
        return f"Node({self.short_id}@{self.ip}:{self.port})"
