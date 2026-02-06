# Quick Reference Guide

## 📋 What Changed

Your system evolved from **centralized server** → **decentralized P2P network** (like BitTorrent).

```
OLD:  Client → Server (single point of failure)
NEW:  Peer ↔ Peer ↔ Peer (decentralized via DHT)
```

---

## 🚀 Getting Started (5 minutes)

### 1. Start a Node
```python
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
    await node.initialize()
    node.start_server()
    print("✓ Node running on port 9000")
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
```

### 2. Store a File
```bash
python main.py store myfile.txt
# Output: File stored with hash: abc123def456...
```

### 3. Download from Network
```python
import asyncio
from src.network.p2p_client_new import P2PClient

async def main():
    client = P2PClient(
        dht_bootstrap_nodes=[("127.0.0.1", 8468)],
        download_dir="downloads"
    )
    await client.initialize()
    
    # Replace with actual hash from step 2
    await client.download_file("abc123def456...")
    
    await client.shutdown()

asyncio.run(main())
```

---

## 📦 Core Components

### P2PPeerManager
**Purpose**: Find peers with chunks via DHT

```python
from src.network.p2p_peer_manager import P2PPeerManager

# Find peers with a chunk
peers = await manager.find_peers_with_chunk("chunk_hash")
for peer in peers:
    print(f"Peer at {peer.ip}:{peer.port}")

# Find peers for all chunks (parallel)
chunk_peers = await manager.find_peers_with_chunks([
    "chunk_1", "chunk_2", "chunk_3"
])

# Register your chunks in DHT
await manager.register_chunks_in_dht([
    "chunk_1", "chunk_2"
])
```

### P2PChunkDownloader
**Purpose**: Download chunks from multiple peers

```python
from src.network.p2p_chunk_downloader import P2PChunkDownloader

downloader = P2PChunkDownloader("downloads", timeout=30, max_connections=5)

# Download from specific peer
data = await downloader.download_chunk(
    "chunk_hash",
    "peer_ip",
    peer_port
)

# Download multiple chunks in parallel
results = await downloader.download_chunks_parallel({
    "chunk_1": [("ip1", 9000), ("ip2", 9000)],
    "chunk_2": [("ip3", 9000)],
})

# Download with automatic fallback
data = await downloader.download_with_retry(
    "chunk_hash",
    [("ip1", 9000), ("ip2", 9000), ("ip3", 9000)],
    max_retries=3
)
```

### P2PNode
**Purpose**: Complete node (serve + download)

```python
from src.network.p2p_node import P2PNode

node = P2PNode(...)
await node.initialize()        # Setup & register local chunks
node.start_server()            # Start serving chunks

# Download file via peers
success = await node.download_file_from_peers(
    "file_hash",
    "output_dir"
)

await node.shutdown()
```

### P2PClient
**Purpose**: Download-only client (no serving)

```python
from src.network.p2p_client_new import P2PClient

client = P2PClient(
    dht_bootstrap_nodes=[("127.0.0.1", 8468)],
    download_dir="downloads"
)

await client.initialize()
await client.download_file("file_hash")
await client.shutdown()
```

---

## 🔍 Common Tasks

### Find which peers have a chunk
```python
peers = await peer_manager.find_peers_with_chunk("abc123")
print(f"Found {len(peers)} peers")
for peer in peers:
    print(f"  - {peer.ip}:{peer.port}")
```

### Download a chunk
```python
data = await downloader.download_chunk(
    chunk_hash="abc123",
    peer_ip="192.168.1.100",
    peer_port=9000
)
if data:
    print(f"Downloaded {len(data)} bytes")
```

### Download multiple chunks in parallel
```python
peers_map = {
    "chunk_1": [("192.168.1.1", 9000)],
    "chunk_2": [("192.168.1.2", 9000)],
    "chunk_3": [("192.168.1.1", 9000)],
}

results = await downloader.download_chunks_parallel(peers_map)
for chunk_hash, data in results.items():
    if data:
        print(f"✓ Downloaded {chunk_hash[:8]}...")
    else:
        print(f"✗ Failed {chunk_hash[:8]}...")
```

### Register chunks in DHT
```python
chunks = ["chunk_hash_1", "chunk_hash_2", "chunk_hash_3"]
await peer_manager.register_chunks_in_dht(chunks)
print(f"Registered {len(chunks)} chunks in DHT")
```

### Publish file metadata
```python
from src.network.p2p_peer_manager import FileMetadata

file_meta = FileMetadata(
    file_hash="file_abc123",
    original_name="document.pdf",
    size=1048576,
    data_chunks=["chunk_1", "chunk_2"],
    parity_chunks=[]
)

await peer_manager.publish_file_metadata(file_meta)
print("✓ File metadata published to DHT")
```

### Discover file from network
```python
file_meta = await peer_manager.discover_file("file_abc123")
if file_meta:
    print(f"Found: {file_meta.original_name}")
    print(f"Size: {file_meta.size} bytes")
    print(f"Chunks: {len(file_meta.data_chunks)}")
else:
    print("File not found in network")
```

---

## 🔐 Network Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8468 | UDP | DHT (peer discovery) |
| 9000 | TCP | Node 1 (chunk serving) |
| 9001 | TCP | Node 2 (chunk serving) |
| 9002 | TCP | Node 3 (chunk serving) |
| ... | TCP | More nodes... |

**Note**: Each node needs unique TCP port for serving chunks.

---

## 📊 Architecture Comparison

### Centralized (OLD)
```
Problem:
├─ Server bottleneck
├─ Single point of failure
├─ Hard to scale
└─ Limited by server bandwidth

File Download:
Client → Server → File
(one source, limited speed)
```

### P2P Decentralized (NEW)
```
Benefits:
├─ No bottleneck
├─ Multiple sources
├─ Scales automatically
└─ Bandwidth = sum of peers

File Download:
Client → Peer1 (chunk1) ─┐
      ↘ Peer2 (chunk2) ─┤ File
      ↘ Peer3 (chunk3) ─┴ (parallel)
      ↘ Peer1 (chunk4) ───┘
```

---

## 🔄 Data Flow

### Storing a File
```
1. python main.py store file.txt
   └─ CAS breaks into chunks
   └─ Each chunk hashed (SHA-256)
   └─ Stored in storage/hashed_files/
   └─ Metadata in cas_index.json

2. Node registers chunks in DHT
   └─ "chunk_hash_1" → {ip, port, node_id}
   └─ "chunk_hash_2" → {ip, port, node_id}
   └─ ...

3. Node publishes file metadata
   └─ "file_metadata:file_hash" → {name, size, chunks}
```

### Downloading a File
```
1. Client queries DHT: "Where is file_hash?"
   └─ DHT: "Found at node_xyz"

2. Client queries DHT: "Who has chunk_1, chunk_2, ...?"
   └─ DHT: "chunk_1 at Peer1, Peer2"
   └─ DHT: "chunk_2 at Peer2, Peer3"
   └─ DTH: "chunk_3 at Peer1, Peer3"

3. Client downloads in parallel
   └─ Ask Peer1 for chunk_1
   └─ Ask Peer2 for chunk_2 (simultaneous)
   └─ Ask Peer3 for chunk_3 (simultaneous)
   └─ Ask Peer1 for chunk_4 (reuse connection)

4. Client verifies hashes
   └─ Check each chunk's SHA-256

5. Client assembles file
   └─ Combine chunks → original file
```

---

## 🐛 Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "Connection refused" | Peer not running | Start peer: `node.start_server()` |
| "DHT bootstrap failed" | No DHT node running | Start at least one node first |
| "Chunk not found" | Chunk not registered | Call `register_chunks_in_dht()` |
| "Download slow" | Only 1 peer available | Start more nodes for parallelism |
| "Port already in use" | Port taken | Use different port number |
| "File not found" | Not published to DHT | Call `publish_file_metadata()` |

---

## 📈 Performance Tips

### Speed Up Downloads
```python
# Increase parallel connections
downloader = P2PChunkDownloader(
    storage_dir="downloads",
    max_connections=10  # Higher = faster (if peers available)
)

# Download from multiple peers for same chunk
peers_map = {
    "chunk_1": [("ip1", 9000), ("ip2", 9000)],  # Fallback
    "chunk_2": [("ip3", 9000)],
}
```

### Optimize Network
```python
# More peers = faster downloads
# More nodes = better redundancy
# Connection pooling = less overhead

# Start multiple nodes for testing
Node1: port 9000
Node2: port 9001
Node3: port 9002
```

### Monitor Performance
```python
# Check peer count
peers = manager.get_peers_with_capacity()
print(f"Network: {len(peers)} peers")

# Check chunk coverage
for chunk_hash, peers in chunk_peers.items():
    print(f"{chunk_hash[:8]}...: {len(peers)} peers")
```

---

## 🔑 Key Concepts

### DHT (Distributed Hash Table)
- Decentralized database
- Maps keys → values
- "Who has chunk X?" → DHT finds answer
- Run on UDP (ports 8468+)

### P2P (Peer-to-Peer)
- Direct connection between peers
- No central server
- Each node is both client and server
- Run on TCP (ports 9000+)

### CAS (Content-Addressable Storage)
- Files identified by hash, not name
- Hash = SHA-256(content)
- Same content = same hash
- Corrupted file = different hash

### Chunks
- Large files split into pieces
- Each chunk hashed separately
- Enables parallel downloading
- Enables redundancy

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `docs/P2P_ARCHITECTURE.md` | Complete technical details |
| `docs/MIGRATION_GUIDE.md` | How to migrate from old system |
| `docs/IMPLEMENTATION_SUMMARY.md` | What was built |
| `examples.py` | Runnable code examples |

---

## 🎯 Next Steps

1. **Test the system**: Run examples.py
2. **Read full docs**: See P2P_ARCHITECTURE.md
3. **Integrate**: Update your main.py
4. **Deploy**: Setup bootstrap nodes
5. **Monitor**: Add logging and metrics

---

## 💡 Pro Tips

### Running Multiple Nodes Locally
```bash
# Terminal 1: Node1
python -c "from src.network.p2p_node import P2PNode; ..." &

# Terminal 2: Node2 (joins Node1)
python -c "from src.network.p2p_node import P2PNode; ..." &

# Terminal 3: Client
python -c "from src.network.p2p_client_new import P2PClient; ..."
```

### Debugging Peer Discovery
```python
# Check what nodes are in DHT
nodes = node.dht_node.routing_table.get_all_nodes()
for n in nodes:
    print(f"Node: {n.ip}:{n.port}")

# Check local chunks
print(f"Local chunks: {len(manager.local_chunks)}")

# Check known peers
peers = manager.get_peers_with_capacity()
print(f"Known peers: {len(peers)}")
```

### Testing Chunk Download
```python
# Simple test
data = await downloader.download_chunk(
    "test_chunk_hash",
    "127.0.0.1",
    9000
)
if data:
    print(f"✓ Downloaded {len(data)} bytes")
else:
    print("✗ Download failed")
```

---

## ✅ Checklist for Production

- [ ] Setup 3+ bootstrap nodes
- [ ] Configure firewall (DHT UDP + P2P TCP)
- [ ] Test peer discovery
- [ ] Test parallel downloads
- [ ] Setup monitoring/logging
- [ ] Test with large files
- [ ] Test network failures
- [ ] Document your setup
- [ ] Train users on client usage

---

**Need more help?** See the full docs:
- **Architecture**: `docs/P2P_ARCHITECTURE.md`
- **Migration**: `docs/MIGRATION_GUIDE.md`
- **Summary**: `docs/IMPLEMENTATION_SUMMARY.md`
