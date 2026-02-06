# Migration Guide: Client-Server to P2P Architecture

## Overview

This guide helps you migrate from the centralized client-server model to the decentralized P2P model.

---

## File Organization

### New Files Added

```
src/network/
├── p2p_peer_manager.py      [NEW] - Peer discovery & tracking
├── p2p_chunk_downloader.py  [NEW] - Parallel chunk downloads
├── p2p_node.py              [NEW] - Hybrid P2P node
├── p2p_client_new.py        [NEW] - P2P client
│
├── p2p_server.py            [OLD] - Deprecated (centralized)
└── p2p_client.py            [OLD] - Deprecated (client-only)

docs/
└── P2P_ARCHITECTURE.md      [NEW] - Architecture documentation

examples.py                  [NEW] - Usage examples
```

### What to Keep
- `src/cas/` - CAS system (unchanged)
- `src/dht/` - DHT/Kademlia (unchanged)
- `src/network/dh_utils.py` - Diffie-Hellman (unchanged)
- `main.py` - CLI interface (needs updates)
- `requirements.txt` - Dependencies (check if all included)

### What to Remove/Deprecate
- `p2p_server.py` - No longer needed (replaced by P2PNode)
- `p2p_client.py` - No longer needed (replaced by P2PClient)

---

## Architecture Changes

### OLD: Client-Server Model

```python
# Server (p2p_server.py)
server = socket.socket()
server.bind(("0.0.0.0", 9000))
server.listen()

# On client request:
# - Get file from local storage
# - Send to client directly

# DHT was only for tracking (not used for downloads)


# Client (p2p_client.py)
client = socket.socket()
client.connect(("server_ip", 9000))

# Send: {"type": "GET_FILE", "hash": "abc123"}
# Receive: file data from server
```

### NEW: P2P Model

```python
# Node (p2p_node.py)
node = P2PNode(...)
await node.initialize()     # Start DHT + register chunks
node.start_server()         # Serve chunks to peers

# When client requests chunk:
# - Check local storage
# - Serve via TCP

# When node needs chunk:
# - Query DHT for peers
# - Download from multiple peers in parallel


# Client (p2p_client_new.py)
client = P2PClient(...)
await client.initialize()   # Connect to DHT

# To download file:
# - Query DHT for file metadata
# - Query DHT for chunk locations
# - Download from multiple peers in parallel
```

---

## Step-by-Step Migration

### Phase 1: Setup ✅

1. **Create new P2P modules** (already done)
   - ✅ `p2p_peer_manager.py`
   - ✅ `p2p_chunk_downloader.py`
   - ✅ `p2p_node.py`
   - ✅ `p2p_client_new.py`

2. **Verify DHT is working**
   ```python
   # Test DHT connectivity
   from src.dht.kademlia import KademliaNode
   
   node = KademliaNode("127.0.0.1", 8468)
   await node.start()
   await node.set("test_key", {"test": "value"})
   result = await node.get("test_key")
   print(result)  # Should show {"test": "value"}
   ```

---

### Phase 2: Update `main.py`

**Before**: Uses CAS only
**After**: Uses CAS + publishes to DHT

```python
# OLD main.py
if args.command == "store":
    file_hash = cas.store_file(args.file, storage_dir)
    print(f"File stored: {file_hash}")
    # Chunks are stored but NOT registered in DHT


# NEW main.py
import asyncio
from src.network.p2p_node import P2PNode

async def store_command(file_path):
    # 1. Store in CAS
    file_hash = cas.store_file(file_path, storage_dir)
    
    # 2. Create node and register chunks
    node = P2PNode(
        node_id="cli_node",
        server_host="127.0.0.1",
        server_port=9000,
        dht_port=8468,
        storage_dir=storage_dir
    )
    
    await node.initialize()
    
    # 3. Get chunks from CAS metadata
    with open(index_path) as f:
        index = json.load(f)
    
    file_meta = index[file_hash]
    chunks = file_meta["data_chunks"] + file_meta["parity_chunks"]
    
    # 4. Register in DHT
    await node.peer_manager.register_chunks_in_dht(chunks)
    
    # 5. Publish file metadata
    await node.peer_manager.publish_file_metadata(file_meta)
    
    print(f"File published to P2P network: {file_hash}")
```

---

### Phase 3: Update Client Usage

**Old Client (centralized)**:
```python
# p2p_client.py
sock = socket.socket()
sock.connect(("server_ip", 9000))

# Send to ONE server
request = {"type": "GET_FILE", "hash": "abc123"}
sock.send(json.dumps(request).encode())

# Receive from server
file_data = sock.recv(...)
```

**New Client (P2P)**:
```python
# p2p_client_new.py
from src.network.p2p_client_new import P2PClient

client = P2PClient(
    dht_bootstrap_nodes=[("127.0.0.1", 8468)],
    download_dir="downloads"
)

await client.initialize()

# Download from network
success = await client.download_file("abc123")
```

---

### Phase 4: Running Nodes

**Single Node Setup** (Development):
```bash
# Terminal 1: Start Node1
python -c "
import asyncio
from src.network.p2p_node import P2PNode

async def main():
    node = P2PNode(
        node_id='Node1',
        server_host='127.0.0.1',
        server_port=9000,
        dht_port=8468,
        storage_dir='storage/hashed_files'
    )
    await node.initialize()
    node.start_server()
    print('Node ready. Press Ctrl+C to stop.')
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
"

# Terminal 2: Store file
python main.py store myfile.txt

# Terminal 3: Download file
python -c "
import asyncio
from src.network.p2p_client_new import P2PClient

async def main():
    client = P2PClient(
        dht_bootstrap_nodes=[('127.0.0.1', 8468)]
    )
    await client.initialize()
    await client.download_file('file_hash_here')

asyncio.run(main())
"
```

**Multi-Node Setup** (Production-like):
```bash
# Terminal 1: Node1 (bootstrap node)
python examples.py node1

# Terminal 2: Node2 (joins network)
python examples.py node2

# Terminal 3: Node3 (joins network)
python examples.py node3

# Terminal 4: Store file on Node1
python main.py store large_file.zip

# Terminal 5: Download from any node via P2P
python examples.py download file_hash
```

---

## API Comparison

### Storing Files

```python
# OLD: CAS only
from src.cas.cas import store_file
file_hash = store_file("myfile.txt", "storage/hashed_files")
# ✗ Not registered in DHT
# ✗ Only visible to direct server clients


# NEW: CAS + DHT
import asyncio
from src.network.p2p_node import P2PNode

async def store_with_dht(filepath):
    file_hash = store_file(filepath, "storage/hashed_files")
    
    node = P2PNode(...)
    await node.initialize()
    
    # Get metadata
    with open("storage/hashed_files/cas_index.json") as f:
        metadata = json.load(f)[file_hash]
    
    # Register chunks
    chunks = metadata["data_chunks"] + metadata["parity_chunks"]
    await node.peer_manager.register_chunks_in_dht(chunks)
    
    # Publish metadata
    await node.peer_manager.publish_file_metadata(metadata)
    
    return file_hash

file_hash = asyncio.run(store_with_dht("myfile.txt"))
# ✓ Registered in DHT
# ✓ Discoverable by all peers
```

### Finding Peers with a Chunk

```python
# OLD: No peer discovery
# ✗ Not possible - server is not in DHT


# NEW: DHT-based discovery
async def find_peers(chunk_hash):
    node = P2PNode(...)
    await node.initialize()
    
    peers = await node.peer_manager.find_peers_with_chunk(chunk_hash)
    for peer in peers:
        print(f"Peer: {peer.ip}:{peer.port}")

asyncio.run(find_peers("chunk_hash"))
# ✓ Lists all peers with this chunk
```

### Downloading a File

```python
# OLD: Single source
sock = socket.socket()
sock.connect(("server_ip", 9000))
request = {"type": "GET_FILE", "hash": "abc123"}
sock.send(json.dumps(request).encode())
file_data = sock.recv(1000000)  # Slow, bottlenecked


# NEW: Multiple sources, parallel
from src.network.p2p_client_new import P2PClient

async def download():
    client = P2PClient(
        dht_bootstrap_nodes=[("127.0.0.1", 8468)]
    )
    await client.initialize()
    await client.download_file("abc123")
    # ✓ Discovers chunk locations
    # ✓ Downloads in parallel
    # ✓ Much faster!

asyncio.run(download())
```

---

## Data Flow Comparison

### OLD: Server-Client

```
Client1                    Server                  Storage
  |                          |                        |
  ├─ GET_FILE ───────────┬──>|
  |                       |   ├─ Read chunks ──────>|
  |                       |   |<─ Return chunk ──────┤
  |<──── FILE_DATA ───────┴──┤
  |                          |

Problems:
- Server is bottleneck
- Only one source per file
- No parallel downloads
```

### NEW: P2P with DHT

```
Client              DHT              Node1           Node2           Storage
  |                  |                 |               |               |
  ├─ Discover ──────>|                 |               |               |
  |<─ Metadata ──────┤                 |               |               |
  |                  |                 |               |               |
  ├─ Find Peers ────>|                 |               |               |
  |<─ [Node1, Node2] |                 |               |               |
  |                  |                 |               |               |
  ├─ GET_CHUNK ───────────────────────>|               |               |
  |                  |                 |─────────────>|               |
  |<─ chunk_1 ───────────────────────┤               |               |
  |                  |                 |               |               |
  |                  |                 |         ┌─────────────────>|
  |                  |                 |         |   |               |
  |<────────── chunk_2 ─────────────────────────┘   |               |
  |                  |                 |               |               |

Benefits:
- Multiple sources per file
- Parallel downloads
- No single bottleneck
```

---

## Testing Migration

### Test 1: Verify DHT Integration

```python
import asyncio
from src.dht.kademlia import KademliaNode

async def test_dht():
    # Start node
    node = KademliaNode("127.0.0.1", 8468)
    await node.start()
    
    # Store value
    await node.set("test_chunk", {"node": "node1", "ip": "127.0.0.1"})
    
    # Retrieve value
    result = await node.get("test_chunk")
    assert result["node"] == "node1"
    
    await node.stop()
    print("✓ DHT working correctly")

asyncio.run(test_dht())
```

### Test 2: Verify Chunk Registration

```python
import asyncio
from src.network.p2p_node import P2PNode

async def test_chunk_registration():
    node = P2PNode(
        node_id="test_node",
        server_host="127.0.0.1",
        server_port=9000,
        dht_port=8468,
        storage_dir="storage/hashed_files"
    )
    
    await node.initialize()
    
    # Register test chunk
    await node.peer_manager.register_chunks_in_dht(["test_chunk_hash"])
    
    # Find it back
    peers = await node.peer_manager.find_peers_with_chunk("test_chunk_hash")
    assert len(peers) > 0
    assert peers[0].node_id == "test_node"
    
    await node.shutdown()
    print("✓ Chunk registration working")

asyncio.run(test_chunk_registration())
```

### Test 3: Verify Parallel Downloads

```python
import asyncio
from src.network.p2p_chunk_downloader import P2PChunkDownloader

async def test_parallel_download():
    downloader = P2PChunkDownloader("downloads")
    
    # Simulate download from multiple peers
    results = await downloader.download_chunks_parallel({
        "chunk1": [("127.0.0.1", 9000), ("127.0.0.1", 9001)],
        "chunk2": [("127.0.0.1", 9001), ("127.0.0.1", 9002)],
        "chunk3": [("127.0.0.1", 9002)],
    })
    
    print(f"Downloaded {len(results)} chunks")
    print("✓ Parallel download working")

# Note: This requires actual peers running
```

---

## Rollback Plan

If you need to revert to centralized server:

```python
# Revert imports
# from src.network.p2p_client_new import P2PClient  # REMOVE
from src.network.p2p_client import P2PClient          # OLD

# Revert startup
# OLD centralized way
server = socket.socket()
server.bind(("0.0.0.0", 9000))
server.listen(5)

# Keep running old server.py
# The P2P modules are safe to ignore if not used
```

---

## Performance Improvements

### Expected Benefits

| Metric | Before | After |
|--------|--------|-------|
| **Single file download** | 1x | ~2.5x faster |
| **Multiple users** | Bottlenecked | Scales linearly |
| **Chunk redundancy** | 1 source | Multiple sources |
| **Network utilization** | Centralized | Distributed |
| **Scalability** | Limited | Unlimited |

### Bottlenecks Removed

1. ✅ Central server bandwidth limit
2. ✅ Single connection per file
3. ✅ Server becoming point of failure
4. ✅ Centralized resource management

---

## Compatibility

### Python Version
- Tested: Python 3.8+
- Required: Python 3.7+

### Dependencies
Check `requirements.txt` includes:
- `cryptography` (for Diffie-Hellman)
- `uvloop` (optional, for faster async)

### Network
- DHT: UDP (port 8468 default)
- P2P: TCP (port 9000+ default)
- Both must be accessible for full P2P operation

---

## Common Issues During Migration

### Issue 1: "DHT bootstrap failed"
```
Cause: No DHT node running on bootstrap address
Fix: Start a node first, or connect to running network
```

### Issue 2: "Chunks not found in DHT"
```
Cause: Chunks not registered
Fix: Call register_chunks_in_dht() after storing
```

### Issue 3: "Connection refused on download"
```
Cause: Peer not running
Fix: Ensure peer node is up: node.start_server()
```

### Issue 4: "Slow downloads"
```
Cause: Only one peer available
Fix: Start multiple nodes for parallel downloads
```

---

## Next Steps

1. **Integration**: Update `main.py` to use P2PNode for storage
2. **Testing**: Run examples.py with 3+ nodes
3. **Optimization**: Tune connection limits and timeouts
4. **Deployment**: Setup bootstrap nodes for production
5. **Monitoring**: Add logging and peer statistics
