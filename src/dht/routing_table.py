"""
Kademlia Routing Table Implementation

The routing table uses k-buckets to organize known nodes by XOR distance.
Each bucket holds up to k nodes, and there are 160 buckets (one per bit position).
"""

import threading
import time
from typing import List, Optional
from .node import Node, xor_distance, get_prefix_length, ID_BITS


# Kademlia parameters
K = 20  # Maximum nodes per bucket (replication factor)
BUCKET_REFRESH_INTERVAL = 3600  # Refresh buckets every hour


class KBucket:
    """
    A k-bucket holds up to K nodes at a specific distance range.
    
    Nodes are ordered by last-seen time (most recently seen at the end).
    When the bucket is full and a new node is seen:
    - If the oldest node responds to ping, keep it and ignore new node
    - If the oldest node doesn't respond, evict it and add new node
    """
    
    def __init__(self, k: int = K):
        self.k = k
        self.nodes: List[Node] = []
        self.replacement_cache: List[Node] = []  # Nodes waiting for a spot
        self.last_updated = time.time()
        self._lock = threading.RLock()
    
    def add(self, node: Node) -> Optional[Node]:
        """
        Add a node to the bucket.
        
        Args:
            node: Node to add
        
        Returns:
            None if added successfully,
            The oldest node if bucket is full (needs ping check)
        """
        with self._lock:
            # If node already exists, move it to the end (most recently seen)
            for i, existing in enumerate(self.nodes):
                if existing.node_id == node.node_id:
                    existing.update_last_seen()
                    # Move to end
                    self.nodes.append(self.nodes.pop(i))
                    self.last_updated = time.time()
                    return None
            
            # If bucket has space, add the node
            if len(self.nodes) < self.k:
                self.nodes.append(node)
                self.last_updated = time.time()
                return None
            
            # Bucket is full - add to replacement cache and return oldest
            if node not in self.replacement_cache:
                self.replacement_cache.append(node)
                # Keep replacement cache bounded
                if len(self.replacement_cache) > self.k:
                    self.replacement_cache.pop(0)
            
            return self.nodes[0]  # Return oldest for ping check
    
    def remove(self, node: Node) -> bool:
        """
        Remove a node from the bucket.
        
        If there are nodes in the replacement cache, promote one.
        
        Returns:
            True if node was found and removed
        """
        with self._lock:
            for i, existing in enumerate(self.nodes):
                if existing.node_id == node.node_id:
                    self.nodes.pop(i)
                    # Promote from replacement cache if available
                    if self.replacement_cache:
                        self.nodes.append(self.replacement_cache.pop(0))
                    self.last_updated = time.time()
                    return True
            return False
    
    def get_nodes(self) -> List[Node]:
        """Get a copy of all nodes in the bucket."""
        with self._lock:
            return list(self.nodes)
    
    def contains(self, node: Node) -> bool:
        """Check if node is in this bucket."""
        with self._lock:
            return any(n.node_id == node.node_id for n in self.nodes)
    
    def __len__(self) -> int:
        return len(self.nodes)
    
    def __repr__(self) -> str:
        return f"KBucket({len(self.nodes)}/{self.k} nodes)"


class RoutingTable:
    """
    Kademlia routing table with 160 k-buckets.
    
    Bucket i contains nodes with XOR distance in range [2^i, 2^(i+1)).
    This means:
    - Bucket 0: nodes that differ in the last bit only (very close)
    - Bucket 159: nodes that differ in the first bit (very far)
    
    The table maintains more contacts for nodes close to us,
    which is optimal for the iterative lookup algorithm.
    """
    
    def __init__(self, local_node: Node, k: int = K):
        self.local_node = local_node
        self.k = k
        self.buckets: List[KBucket] = [KBucket(k) for _ in range(ID_BITS)]
        self._lock = threading.RLock()
    
    def get_bucket_index(self, node_id: bytes) -> int:
        """
        Get the bucket index for a node ID.
        
        The bucket index is based on the XOR distance prefix length.
        """
        distance = xor_distance(self.local_node.node_id, node_id)
        if distance == 0:
            return 0  # Same node as us
        # Bucket index is 159 - number of leading zeros
        # Or equivalently: bit_length - 1
        return distance.bit_length() - 1
    
    def add_node(self, node: Node) -> Optional[Node]:
        """
        Add a node to the appropriate bucket.
        
        Args:
            node: Node to add
        
        Returns:
            None if added, or oldest node if ping check needed
        """
        # Don't add ourselves
        if node.node_id == self.local_node.node_id:
            return None
        
        bucket_idx = self.get_bucket_index(node.node_id)
        return self.buckets[bucket_idx].add(node)
    
    def remove_node(self, node: Node) -> bool:
        """Remove a node from the routing table."""
        bucket_idx = self.get_bucket_index(node.node_id)
        return self.buckets[bucket_idx].remove(node)
    
    def get_closest_nodes(self, target_id: bytes, count: int = K) -> List[Node]:
        """
        Get the k closest nodes to a target ID.
        
        This is the core operation for Kademlia lookups.
        We search through all buckets and return nodes sorted by XOR distance.
        
        Args:
            target_id: The target node ID to find closest nodes to
            count: Maximum number of nodes to return
        
        Returns:
            List of nodes sorted by XOR distance to target
        """
        all_nodes = []
        with self._lock:
            for bucket in self.buckets:
                all_nodes.extend(bucket.get_nodes())
        
        # Sort by XOR distance to target
        all_nodes.sort(key=lambda n: xor_distance(n.node_id, target_id))
        
        return all_nodes[:count]
    
    def get_all_nodes(self) -> List[Node]:
        """Get all nodes in the routing table."""
        all_nodes = []
        with self._lock:
            for bucket in self.buckets:
                all_nodes.extend(bucket.get_nodes())
        return all_nodes
    
    def get_bucket_for_node(self, node: Node) -> KBucket:
        """Get the bucket that a node belongs to."""
        bucket_idx = self.get_bucket_index(node.node_id)
        return self.buckets[bucket_idx]
    
    def get_stale_buckets(self) -> List[int]:
        """Get indices of buckets that haven't been updated recently."""
        stale = []
        now = time.time()
        for i, bucket in enumerate(self.buckets):
            if len(bucket) > 0 and (now - bucket.last_updated) > BUCKET_REFRESH_INTERVAL:
                stale.append(i)
        return stale
    
    def total_nodes(self) -> int:
        """Get total number of nodes in routing table."""
        return sum(len(b) for b in self.buckets)
    
    def __repr__(self) -> str:
        non_empty = sum(1 for b in self.buckets if len(b) > 0)
        return f"RoutingTable({self.total_nodes()} nodes in {non_empty} buckets)"
    
    def debug_print(self):
        """Print routing table state for debugging."""
        print(f"\n=== Routing Table for {self.local_node} ===")
        print(f"Total nodes: {self.total_nodes()}")
        for i, bucket in enumerate(self.buckets):
            if len(bucket) > 0:
                print(f"  Bucket {i}: {bucket}")
                for node in bucket.get_nodes():
                    dist = xor_distance(self.local_node.node_id, node.node_id)
                    print(f"    - {node} (distance: {dist})")
        print("=" * 50)
