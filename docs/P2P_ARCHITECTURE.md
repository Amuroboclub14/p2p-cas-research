# P2P File Sharing Architecture Guide

## Overview

Your system has been transformed from a centralized **Client-Server** model to a decentralized **Peer-to-Peer (P2P)** model similar to BitTorrent, using DHT for peer discovery.

### Before vs After

```
BEFORE (Centralized):
┌─────────────────────────────────────────┐
│  Central Server (File Host)             │
│  - Stores all chunks                    │
│  - Serves all clients                   │
│  - Single point of failure              │
└─────────────────────────────────────────┘
         ↓        ↓        ↓
    Client   Client   Client
    (Only download)


AFTER (P2P with DHT):
┌──────────────────────────────────────────┐
│           DHT Network                     │
│  (Peer Discovery & Chunk Location)       │
│  - Tracks which peer has which chunk     │
│  - Decentralized                         │
│  - Scalable                              │
└──────────────────────────────────────────┘
         ↓        ↓        ↓
     Node A    Node B    Node C
   (Serve &   (Serve &  (Serve &
   Download) Download) Download)
```

---

## Key Components

### 1. **P2PPeerManager** (`p2p_peer_manager.py`)
**Purpose**: Manages peer discovery and chunk location lookup.

**Key Features**:
- **Peer Tracking**: Maintains list of known peers and which chunks they have
- **DHT Queries**: Uses DHT to find which peers have specific chunks
- **File Metadata**: Publishes and discovers file metadata through DHT
- **Multi-peer Lookup**: Can find multiple peers for each chunk (fallback options)

**Key Methods**:
```python
# Find which peer has a chunk
peers = await peer_manager.find_peers_with_chunk("chunk_hash_abc123")

# Find peers for all chunks of a file
chunk_peers = await peer_manager.find_peers_with_chunks([
    "chunk_hash_1",
    "chunk_hash_2",
    ...
])

# Publish that we have chunks
await peer_manager.register_chunks_in_dht([
    "chunk_hash_1",
    "chunk_hash_2"
])

# Publish file metadata so others can discover it
await peer_manager.publish_file_metadata(file_metadata)
```

**DHT Keys Used**:
- `chunk_hash` → PeerInfo (who has this chunk)
- `file_metadata:{file_hash}` → FileMetadata (file info & chunks)

---

### 2. **P2PChunkDownloader** (`p2p_chunk_downloader.py`)
**Purpose**: Downloads chunks from multiple peers in parallel (BitTorrent-style).

**Key Features**:
- **Parallel Downloads**: Downloads from multiple peers simultaneously
- **Connection Pooling**: Controls concurrent connections (default: 5)
- **Hash Verification**: Verifies chunk integrity after download
- **Fallback Strategy**: Tries alternative peers if one fails
- **Timeout Handling**: Prevents hanging on slow/dead peers

**Key Methods**:
```python
# Download single chunk
chunk_data = await downloader.download_chunk(
    "chunk_hash",
    "peer_ip",
    peer_port
)

# Download multiple chunks in parallel
results = await downloader.download_chunks_parallel({
    "chunk_hash_1": [("ip1", port1), ("ip2", port2)],
    "chunk_hash_2": [("ip3", port3)],
    ...
})

# Download with automatic fallback
chunk_data = await downloader.download_with_retry(
    "chunk_hash",
    [("ip1", port1), ("ip2", port2), ("ip3", port3)],
    max_retries=3
)
```

**Protocol** (TCP):
```json
Client -> Server (Request):
{"type": "GET_CHUNK", "chunk_hash": "abc123..."}

Server -> Client (Response):
{"type": "CHUNK_START", "size": 1048576}
[Binary chunk data...]
```

---

### 3. **P2PNode** (`p2p_node.py`)
**Purpose**: Complete P2P node that both serves chunks and downloads from peers.

**Key Features**:
- **Hybrid Architecture**: Acts as both client and server
- **Chunk Server**: Serves chunks to other peers via TCP
- **File Registry**: Maintains local file index
- **DHT Integration**: Registers local chunks in DHT
- **Peer-to-peer Download**: Downloads files using peer discovery

**Architecture**:
```
P2PNode
├── DHT Component (Kademlia Network)
│   └── Peer discovery & chunk location
├── Server Component (TCP listener on port 9000)
│   └── Serves chunks/metadata to peers
├── Peer Manager
│   └── Tracks peers and chunk locations
└── Chunk Downloader
    └── Downloads from discovered peers
```

**Startup Flow**:
1. Initialize DHT node
2. Bootstrap to DHT network
3. Scan local storage for chunks
4. Register chunks in DHT ("I have these chunks")
5. Start TCP server to serve chunks
6. Wait for requests

**Key Methods**:
```python
# Start the node
await node.initialize()
node.start_server()

# Download a file
success = await node.download_file_from_peers(
    "file_hash_abc123",
    "output_directory"
)

# Graceful shutdown
await node.shutdown()
```

---

### 4. **P2PClient** (`p2p_client_new.py`)
**Purpose**: Lightweight client for downloading files from the network.

**Key Features**:
- **DHT-only**: No chunk serving (download-only node)
- **Peer Discovery**: Finds peers for chunks
- **Parallel Download**: Downloads chunks concurrently
- **File Search**: Can search for files in the network

**Usage**:
```python
client = P2PClient(
    dht_bootstrap_nodes=[("127.0.0.1", 8468)],
    download_dir="downloads"
)

await client.initialize()

# List files
files = await client.list_files()

# Download
success = await client.download_file("file_hash_abc123")

await client.shutdown()
```

---

## Download Flow (Step-by-Step)

### Example: Downloading a file with 4 chunks

```
1. CLIENT WANTS FILE (hash: "file_123")
   └─ Query DHT for file metadata

2. DHT RESPONDS with:
   {
     "file_hash": "file_123",
     "original_name": "video.mp4",
     "size": 4194304,
     "data_chunks": [
       "chunk_1_hash",
       "chunk_2_hash", 
       "chunk_3_hash",
       "chunk_4_hash"
     ]
   }

3. CLIENT QUERIES DHT FOR EACH CHUNK:
   ┌─ "Which peers have chunk_1?" → [NodeA, NodeB]
   ├─ "Which peers have chunk_2?" → [NodeB, NodeC]
   ├─ "Which peers have chunk_3?" → [NodeA, NodeC]
   └─ "Which peers have chunk_4?" → [NodeB, NodeD]

4. CLIENT DOWNLOADS IN PARALLEL:
   ┌─ chunk_1 from NodeA ────► 1MB
   ├─ chunk_2 from NodeB ────► 1MB  (simultaneous)
   ├─ chunk_3 from NodeC ────► 1MB
   └─ chunk_4 from NodeD ────► 1MB

5. CLIENT VERIFIES HASHES:
   └─ Each chunk hash is verified

6. FILE RECONSTRUCTED:
   └─ Chunks combined → original file

This is much faster than downloading all from one server!
```

---

## DHT Key Organization

### Storage Structure

```
DHT Network
├── chunk_hashes (Storage)
│   ├── "abc123..." → {"node_id": "X", "ip": "1.2.3.4", "port": 9000}
│   └── "def456..." → {"node_id": "Y", "ip": "5.6.7.8", "port": 9000}
│
├── file_metadata (Discovery)
│   ├── "file_metadata:file_1" → {
│   │     "file_hash": "file_1",
│   │     "original_name": "document.pdf",
│   │     "data_chunks": ["abc123", "def456", ...],
│   │     "parity_chunks": ["parity_1", ...]
│   │   }
│   └── "file_metadata:file_2" → {...}
│
└── peer_lists (Optional future enhancement)
    └── "peers" → List of all active nodes
```

### Publishing Chunks
When a node stores chunks, it registers them:
```python
await peer_manager.register_chunks_in_dht([
    "chunk_hash_1",
    "chunk_hash_2",
    ...
])
# DHT now maps chunk_hash → this_node's_info
```

### Discovering Files
Clients search for file metadata:
```python
file_meta = await peer_manager.discover_file("file_hash")
# Returns file's chunks list
```

---

## Network Protocols

### 1. **DHT Protocol** (UDP - Kademlia)
- Used for peer discovery
- Decentralized by nature
- Handles `ping`, `find_node`, `get`, `set` operations

### 2. **P2P Chunk Transfer Protocol** (TCP)

**GET_CHUNK Request:**
```json
{
  "type": "GET_CHUNK",
  "chunk_hash": "abc123..."
}
```

**CHUNK_START Response:**
```json
{
  "type": "CHUNK_START",
  "size": 1048576
}
[1048576 bytes of binary data]
```

**GET_FILE_METADATA Request:**
```json
{
  "type": "GET_FILE_METADATA",
  "file_hash": "file_123"
}
```

**FILE_METADATA Response:**
```json
{
  "type": "FILE_METADATA",
  "file_hash": "file_123",
  "original_name": "video.mp4",
  "size": 4194304,
  "data_chunks": [...],
  "parity_chunks": [...]
}
```

---

## Benefits of This Architecture

### vs Centralized Server:
| Aspect | Server | P2P |
|--------|--------|-----|
| **Bandwidth** | Server bottleneck | Shared across peers |
| **Scalability** | Limited by server | Grows with network |
| **Availability** | Single point of failure | Distributed redundancy |
| **Download Speed** | Server limit | Multiple sources/peer |
| **Cost** | High (server infrastructure) | Low (peer resources) |
| **Privacy** | Server sees all traffic | Decentralized |

### vs Basic DHT:
- DHT alone is slow for bulk data
- Combining DHT (metadata/discovery) + TCP (bulk data) = optimal
- DHT for "where is X?" + TCP for "send me X's data"

---

## Implementation Checklist

### Phase 1: Core P2P ✅
- [x] P2P Peer Manager (discovery & tracking)
- [x] P2P Chunk Downloader (parallel downloads)
- [x] P2P Node (hybrid server/client)
- [x] P2P Client (lightweight downloader)

### Phase 2: Integration (TODO)
- [ ] Update `main.py` to use P2PNode
- [ ] Create startup scripts for multiple nodes
- [ ] Implement file metadata publishing when storing files
- [ ] Add bandwidth throttling (optional)
- [ ] Add peer reputation system

### Phase 3: Advanced (TODO)
- [ ] Implement Redundancy (Erasure Coding)
- [ ] Add peer caching (prefetch chunks)
- [ ] NAT traversal using DHT
- [ ] Compression support
- [ ] Chunk streaming (start playback before download complete)

---

## Configuration

### Node Startup
```python
node = P2PNode(
    node_id="node_1",
    server_host="0.0.0.0",
    server_port=9000,
    dht_port=8468,
    storage_dir="storage/hashed_files"
)

await node.initialize()
node.start_server()
```

### Client Startup
```python
client = P2PClient(
    dht_bootstrap_nodes=[
        ("node1_ip", 8468),
        ("node2_ip", 8468),
        ("node3_ip", 8468)
    ],
    download_dir="downloads"
)

await client.initialize()
```

### DHT Bootstrap
First node bootstraps to itself:
```python
await dht_node.bootstrap([("127.0.0.1", 8468)])
```

Subsequent nodes bootstrap to first:
```python
await dht_node.bootstrap([("first_node_ip", 8468)])
```

---

## Security Considerations

### Current Implementation:
✅ Hash verification (prevents corruption)
✅ Chunk integrity checking

### Recommended Additions:
- [ ] TLS/SSL encryption for chunk transfer
- [ ] Digital signatures for metadata
- [ ] Peer reputation scoring
- [ ] Bandwidth limiting per peer
- [ ] Rate limiting (prevent DDoS)

---

## Troubleshooting

### Issue: Chunks not found
```
Solution:
1. Check if node is registered in DHT
2. Verify storage_dir has chunks
3. Check DHT connectivity
```

### Issue: Slow downloads
```
Solution:
1. Increase max_concurrent connections
2. Use geographically closer peers
3. Check network latency
```

### Issue: DHT bootstrap fails
```
Solution:
1. Ensure bootstrap node is running
2. Check firewall (UDP port open)
3. Verify IP/port configuration
```

---

## Future Enhancements

1. **Content Delivery Network (CDN)** - Combine with edge servers
2. **Smart Peer Selection** - Choose peers by location/bandwidth
3. **Incentive System** - Reward nodes that share more
4. **Adaptive Streaming** - Stream content while downloading
5. **Network Coding** - Optimal chunk distribution
