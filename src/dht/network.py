"""
Kademlia Network Layer

UDP-based transport for Kademlia RPC messages.
Uses asyncio for async message handling.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from .node import Node


logger = logging.getLogger(__name__)


# Network constants
MESSAGE_TIMEOUT = 5.0  # Seconds to wait for a response
MAX_MESSAGE_SIZE = 65535  # Max UDP datagram size


@dataclass
class PendingRequest:
    """Tracks a pending RPC request awaiting response."""
    future: asyncio.Future
    timestamp: float = field(default_factory=time.time)
    

class KademliaProtocol(asyncio.DatagramProtocol):
    """
    Asyncio UDP protocol for Kademlia messaging.
    
    Handles sending and receiving JSON-encoded RPC messages.
    Each message has a unique ID for request/response correlation.
    """
    
    def __init__(self, local_node: Node, message_handler: Callable):
        self.local_node = local_node
        self.message_handler = message_handler
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.pending_requests: Dict[str, PendingRequest] = {}
        self._next_id = 0
    
    def connection_made(self, transport: asyncio.DatagramTransport):
        """Called when the UDP socket is ready."""
        self.transport = transport
        logger.info(f"Kademlia protocol started on {self.local_node.address}")
    
    def connection_lost(self, exc: Optional[Exception]):
        """Called when the transport is closed."""
        logger.info("Kademlia protocol stopped")
        # Cancel all pending requests
        for request in self.pending_requests.values():
            if not request.future.done():
                request.future.cancel()
    
    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """
        Handle incoming UDP datagram.
        
        Messages are JSON with format:
        {
            "msg_id": "unique-id",
            "type": "request|response",
            "rpc": "PING|FIND_NODE|STORE|FIND_VALUE",
            "sender": {node dict},
            "payload": {...}
        }
        """
        try:
            message = json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Invalid message from {addr}: {e}")
            return
        
        msg_id = message.get('msg_id')
        msg_type = message.get('type')
        
        if msg_type == 'response':
            # This is a response to our request
            self._handle_response(msg_id, message)
        elif msg_type == 'request':
            # This is an incoming request - handle it
            asyncio.create_task(self._handle_request(message, addr))
        else:
            logger.warning(f"Unknown message type from {addr}: {msg_type}")
    
    def _handle_response(self, msg_id: str, message: dict):
        """Handle a response to a pending request."""
        pending = self.pending_requests.pop(msg_id, None)
        if pending and not pending.future.done():
            pending.future.set_result(message)
        elif pending is None:
            logger.debug(f"Received response for unknown request: {msg_id}")
    
    async def _handle_request(self, message: dict, addr: Tuple[str, int]):
        """Handle an incoming RPC request."""
        try:
            # Parse sender node
            sender_data = message.get('sender', {})
            sender = Node.from_dict(sender_data)
            sender.update_last_seen()
            
            # Let the handler process the request
            response_payload = await self.message_handler(
                rpc=message.get('rpc'),
                sender=sender,
                payload=message.get('payload', {}),
                addr=addr
            )
            
            # Send response
            response = {
                'msg_id': message.get('msg_id'),
                'type': 'response',
                'rpc': message.get('rpc'),
                'sender': self.local_node.to_dict(),
                'payload': response_payload
            }
            self._send(response, addr)
            
        except Exception as e:
            logger.error(f"Error handling request from {addr}: {e}")
    
    def _send(self, message: dict, addr: Tuple[str, int]):
        """Send a message to an address."""
        if self.transport is None:
            logger.error("Cannot send - transport not ready")
            return
        
        try:
            data = json.dumps(message).encode('utf-8')
            if len(data) > MAX_MESSAGE_SIZE:
                logger.error(f"Message too large: {len(data)} bytes")
                return
            self.transport.sendto(data, addr)
        except Exception as e:
            logger.error(f"Error sending to {addr}: {e}")
    
    def _generate_msg_id(self) -> str:
        """Generate a unique message ID."""
        self._next_id += 1
        return f"{self.local_node.short_id}-{self._next_id}-{os.urandom(4).hex()}"
    
    async def send_request(
        self, 
        node: Node, 
        rpc: str, 
        payload: dict,
        timeout: float = MESSAGE_TIMEOUT
    ) -> Optional[dict]:
        """
        Send an RPC request and wait for response.
        
        Args:
            node: Target node to send to
            rpc: RPC type (PING, FIND_NODE, etc.)
            payload: Request payload
            timeout: Seconds to wait for response
        
        Returns:
            Response message dict, or None if timeout/error
        """
        msg_id = self._generate_msg_id()
        
        message = {
            'msg_id': msg_id,
            'type': 'request',
            'rpc': rpc,
            'sender': self.local_node.to_dict(),
            'payload': payload
        }
        
        # Create future for response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_requests[msg_id] = PendingRequest(future=future)
        
        # Send the request
        self._send(message, node.address)
        
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.debug(f"Request {rpc} to {node} timed out")
            self.pending_requests.pop(msg_id, None)
            return None
        except asyncio.CancelledError:
            self.pending_requests.pop(msg_id, None)
            return None
    
    def error_received(self, exc: Exception):
        """Handle transport errors."""
        logger.error(f"Transport error: {exc}")


async def create_protocol(
    local_node: Node,
    message_handler: Callable
) -> Tuple[asyncio.DatagramTransport, KademliaProtocol]:
    """
    Create and start a Kademlia UDP protocol.
    
    Args:
        local_node: The local node (with ip and port)
        message_handler: Async function to handle incoming requests
    
    Returns:
        Tuple of (transport, protocol)
    """
    loop = asyncio.get_event_loop()
    
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: KademliaProtocol(local_node, message_handler),
        local_addr=(local_node.ip, local_node.port)
    )
    
    return transport, protocol
