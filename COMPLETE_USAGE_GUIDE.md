# P2P Content-Addressable Storage (CAS) System - Complete Usage Guide

## Project Overview

A **peer-to-peer file sharing system** with:
- **Content-Addressable Storage (CAS)**: Files identified by SHA-256 hash, not by name
- **DHT-based Discovery**: BitTorrent-like peer discovery using Kademlia DHT
- **Erasure Coding (Reed-Solomon)**: File resilience through data + parity chunks
- **Parallel Chunk Download**: Download file chunks from multiple peers simultaneously
- **Hybrid P2P Nodes**: Each node both serves chunks (server) and downloads from peers (client)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    P2P Network                              │
│  (Multiple Nodes communicating via DHT + Direct TCP)        │
└─────────────────────────────────────────────────────────────┘
         ↑                    ↑                    ↑
    ┌────────┐           ┌────────┐          ┌────────┐
    │ Node 1 │           │ Node 2 │          │ Node 3 │
    │ Port   │           │ Port   │          │ Port   │
    │ 9000   │           │ 9001   │          │ 9002   │
    └────────┘           └────────┘          └────────┘
         ↓                    ↓                    ↓
    Storage: hash_files/  Storage: hash_files/ Storage: hash_files/
    
    └──────────────────────────────────────────────────────────┘
                     Shared CAS Index
                  (cas_index.json)
```

### Key Components

1. **DHT (Distributed Hash Table)**
   - Uses Kademlia algorithm (UDP on port 8468, 8469, 8470...)
   - Stores chunk→peer mappings: `chunk_hash → {peer_ip, peer_port}`
   - Stores file metadata: `file_metadata:{file_hash} → {original_name, chunks, size...}`

2. **CAS Storage**
   - Directory: `storage/hashed_files/`
   - Files identified by SHA-256 hash, not name
   - Each file split into 65KB chunks with erasure coding
   - Index: `storage/hashed_files/cas_index.json`

3. **P2P Nodes**
   - TCP Server (port 9000+): Serves chunks to other peers
   - DHT Client: Discovers peers and registers chunks
   - TCP Client: Downloads chunks from other peers

4. **P2P Client** (Download-only)
   - Connects to DHT to discover files
   - Downloads file chunks from peers
   - Does not serve chunks

---

## File Structure & Commands

### Main Entry Points

#### 1. **run_node1.py** / **run_node2.py** / **run_node3.py**
**Purpose**: Start individual P2P nodes on different ports

```bash
# Terminal 1: Start Node 1 (DHT port 8468, Serve port 9000)
python run_node1.py

# Terminal 2: Start Node 2 (DHT port 8469, Serve port 9001)
python run_node2.py

# Terminal 3: Start Node 3 (DHT port 8470, Serve port 9002)
python run_node3.py
```

**What happens:**
- Each node initializes Kademlia DHT
- Scans `storage/hashed_files/` for local chunks
- Registers all chunks in DHT: `chunk_hash → node_info`
- Publishes file metadata for files in `cas_index.json`
- Starts TCP server to serve chunks on 9000/9001/9002
- Waits for requests

**Output to watch for:**
```
[P2P] Initializing node node1
[DHT] Node bootstrapped
[STORAGE] Loaded 42 local chunks
[DHT] Registered chunk: 3bbf337d...
[SERVER] Listening on 127.0.0.1:9000
```

---

#### 2. **main.py**
**Purpose**: Command-line tool to manage CAS (store, list, retrieve files)

```bash
# Store a file into CAS (creates chunks, generates hash, updates index)
python main.py store <file_path>
# Example:
python main.py store test.txt
# Output: File hash: ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28

# List all stored files
python main.py list

# Retrieve (download locally) a file by hash
python main.py retrieve <file_hash> <output_path>
# Example:
python main.py retrieve ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28 test_download.txt
```

**What happens:**
- `store`: Splits file into 65KB chunks → computes SHA-256 → applies Reed-Solomon (4 data + 1 parity)
  - Stores chunks in `storage/hashed_files/`
  - Updates `cas_index.json` with metadata (file hash, original name, chunks list)
- `list`: Reads `cas_index.json` and prints all stored files
- `retrieve`: Reads chunks from local storage and reconstructs file

---

#### 3. **download_file.py**
**Purpose**: Download a file from the P2P network using DHT discovery

```bash
# Edit FILE_HASH in the script, then run:
python download_file.py
```

**Setup:**
1. Open `download_file.py`
2. Replace `FILE_HASH` with the hash you want to download:
   ```python
   FILE_HASH = "ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28"
   ```
3. Run: `python download_file.py`

**What happens:**
- Creates P2P client (ephemeral DHT node on random port)
- Connects to bootstrap DHT node (127.0.0.1:8468)
- Queries DHT for file metadata: `file_metadata:{FILE_HASH}`
- Queries DHT for each chunk location
- Downloads chunks from peers in parallel
- Saves chunks to `downloads/` directory

**Output:**
```
============================================================
P2P File Downloader
============================================================

[CLIENT] Connecting to network...
[DHT] Bootstrap successful
[CLIENT] Downloading file: ace997a024...
[CLIENT] Found: test.txt (38 bytes)
[CLIENT] Finding peers for 1 data chunks...
[CLIENT] Starting parallel download from 1 peers...
[SERVER] Served chunk: ace997a0... to 127.0.0.1:52345
✓ File downloaded to: downloads/
```

---

#### 4. **src/network/p2p_node.py**
**Purpose**: Core P2P node implementation (used by run_node*.py scripts)

Not run directly. Used by:
- `run_node1.py`, `run_node2.py`, `run_node3.py`

Classes provided:
- `P2PNode`: Hybrid node (serves + downloads)
  - `initialize()`: Setup DHT, load chunks, register in DHT
  - `start_server()`: Start TCP chunk server
  - `download_file_from_peers()`: Download file by hash

---

#### 5. **src/network/p2p_client_new.py**
**Purpose**: Interactive P2P client CLI

```bash
# Start interactive client
python src/network/p2p_client_new.py
```

**Commands:**
```
client> list              # List all available files in network
client> download <hash>   # Download file by hash to downloads/
client> quit              # Exit
```

**Example session:**
```
=== P2P File Sharing Client ===
Commands:
  list              - List available files
  download <hash>   - Download file by hash
  quit              - Exit

client> list
Found 3 files:
  - MPI.pdf (2712063 bytes)
    Hash: 57bce1146024afbf79361a393acdcab15849d708bcb8812b22e9b4d61e41b80f
  - test.txt (38 bytes)
    Hash: ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28
client> download ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28
[CLIENT] Downloading file: ace997a024...
✓ Download complete: test.txt
client> quit
```

---

### Support Scripts

#### **run_node.py** (Alternative: Universal node runner)
**Purpose**: Start a node with custom port numbers (alternative to run_node1/2/3)

```bash
python run_node.py --node-id my-node-1 --dht-port 8468 --serve-port 9000
```

**Why use run_node1/2/3 instead:** Simpler, pre-configured, no need to remember port numbers.

---

### Storage & Index Files

#### **storage/hashed_files/**
Directory containing all chunks stored locally.

```
storage/hashed_files/
├── cas_index.json                    # Index of all stored files
├── 3bbf337d397c60faeb72b0b3649f0aa74...  # Chunk file (binary)
├── 523d7fcfae9c3bb48cf1000283cf8f331...  # Chunk file (binary)
├── 5e90a4230e0efab0b8c1763f90be7b3b4...  # Chunk file (binary)
└── ... more chunks ...
```

#### **cas_index.json** Format
```json
{
  "57bce1146024afbf79361a393acdcab15849d708bcb8812b22e9b4d61e41b80f": {
    "hash": "57bce1146024afbf79361a393acdcab15849d708bcb8812b22e9b4d61e41b80f",
    "original_name": "MPI.pdf",
    "size": 2712063,
    "k": 4,
    "m": 1,
    "data_chunks": ["3bbf337d...", "523d7fca...", ...],
    "parity_chunks": ["ab7a5c93..."],
    "chunk_size": 65536,
    "stored_at": "2026-02-05T01:02:12.077",
    "last_accessed": "2026-02-05T01:02:12.077"
  }
}
```

---

## Complete Workflow Example

### Step 1: Start Multiple Nodes

Open **3 Terminal Windows**:

**Terminal 1:**
```bash
cd c:\Users\mohds\OneDrive\Desktop\github\p2p-cas-research
python run_node1.py
```
Output:
```
[P2P] Initializing node node1
[DHT] Node bootstrapped
[STORAGE] Loaded 42 local chunks
[DHT] Registered chunk: 3bbf337d...
[DHT] Registered chunk: 523d7fca...
...
[DHT] Published file metadata: MPI.pdf
[SERVER] Listening on 127.0.0.1:9000
```

**Terminal 2:**
```bash
python run_node2.py
```

**Terminal 3:**
```bash
python run_node3.py
```

All nodes will connect to each other via DHT and register their chunks.

---

### Step 2: Store a File (Optional - Files already stored)

**Terminal 4 (or new window):**
```bash
# Check what files are already stored
python main.py list
```

Output:
```
Stored Files:
├─ MPI.pdf (Hash: 57bce1146024afbf79361a393acdcab15849d708bcb8812b22e9b4d61e41b80f)
│  Size: 2712063 bytes, Chunks: 42 data + 1 parity
├─ test.txt (Hash: ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28)
│  Size: 38 bytes, Chunks: 1 data + 1 parity
```

If you want to store a new file:
```bash
# Create a test file
echo "Hello from P2P network!" > myfile.txt

# Store it
python main.py store myfile.txt
# Output: File hash: d1a6e123abc456def789...

# Verify it's stored
python main.py list
```

---

### Step 3: Download a File from Network

**Terminal 4:**
```bash
# Edit download_file.py and set:
# FILE_HASH = "ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28"

python download_file.py
```

Output:
```
============================================================
P2P File Downloader
============================================================

[CLIENT] Connecting to network...
[DHT] Bootstrap successful
[CLIENT] Downloading file: ace997a024...
[CLIENT] Found: test.txt (38 bytes)
[CLIENT] Finding peers for 1 data chunks...
[CLIENT] Starting parallel download from 1 peers...
✓ File downloaded to: downloads/
```

**Check downloaded file:**
```bash
cat downloads/ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28
```

---

### Step 4: Alternative - Use Interactive Client

```bash
python src/network/p2p_client_new.py
```

Then use commands:
```
client> list
Found 3 files:
  - MPI.pdf (2712063 bytes)
    Hash: 57bce1146024afbf79361a393acdcab15849d708bcb8812b22e9b4d61e41b80f
  - test.txt (38 bytes)
    Hash: ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28
client> download ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28
✓ Download complete: test.txt
```

---

## System Architecture Details

### DHT Operations

#### **Storing a Chunk in DHT**
When a node initializes:
1. Scans `storage/hashed_files/` for chunks
2. For each chunk, calls: `await dht_node.set(chunk_hash, peer_info)`
   - `chunk_hash`: SHA-256 of chunk
   - `peer_info`: `{node_id, ip, port}`
3. DHT replicates across k closest nodes (k=20 by default)

#### **Publishing File Metadata in DHT**
When a node loads local CAS files:
1. Reads `cas_index.json`
2. For each file, calls: `await dht_node.set(f"file_metadata:{file_hash}", metadata)`
   - `file_hash`: SHA-256 of complete file
   - `metadata`: `{original_name, size, data_chunks[], parity_chunks[], ...}`

#### **Discovering a File**
When client wants to download:
1. Calls: `await dht_node.get(f"file_metadata:{file_hash}")`
2. DHT performs iterative lookup (Kademlia algorithm):
   - Query k closest nodes to the key
   - Each node returns k closer nodes
   - Repeat until found or no closer nodes exist
3. Returns file metadata with list of chunk hashes

#### **Finding Peers for Chunks**
1. For each chunk in file, calls: `await dht_node.get(chunk_hash)`
2. Returns list of peers (node_id, ip, port) that have that chunk
3. Client connects to these peers via TCP to download

---

### TCP Chunk Transfer Protocol

#### **Server Side** (Node listening on port 9000)
```
Listen on TCP 9000
  ← Client connects with request:
    {"type": "GET_CHUNK", "chunk_hash": "3bbf337d..."}
  → Send chunk header:
    {"type": "CHUNK_START", "size": 65536}
  → Send 65536 bytes of chunk data
  ← (client disconnects)
```

#### **Client Side** (Downloader)
```
Connect to 127.0.0.1:9000
  → Send: {"type": "GET_CHUNK", "chunk_hash": "3bbf337d..."}
  ← Receive header: {"type": "CHUNK_START", "size": 65536}
  ← Receive 65536 bytes
Save to: storage/hashed_files/3bbf337d...
```

---

### File Storage & Reconstruction

#### **When Storing a File** (main.py store)
```python
file_content = read(input_file)
chunks = split_into_65KB(file_content)  # e.g., 42 chunks for 2.7MB file

# Apply Reed-Solomon erasure coding
# k=4 data chunks → m=1 parity chunk (configurable)
data_chunks = chunks[:4]
parity_chunks = apply_reed_solomon(data_chunks, m=1)

# Compute SHA-256 of each chunk and original file
for chunk in data_chunks + parity_chunks:
    chunk_hash = sha256(chunk)
    save_to(chunk, f"storage/hashed_files/{chunk_hash}")

file_hash = sha256(file_content)
update_cas_index(file_hash, {
    "original_name": "MPI.pdf",
    "size": 2712063,
    "data_chunks": [list of hashes],
    "parity_chunks": [list of hashes],
    "k": 4,
    "m": 1
})
```

#### **When Downloading a File** (download_file.py)
```python
# 1. DHT: Find file metadata
file_meta = await dht.get(f"file_metadata:{file_hash}")

# 2. DHT: Find peers for each chunk
for chunk_hash in file_meta.data_chunks:
    peers = await dht.get(chunk_hash)

# 3. TCP: Download chunks from peers in parallel
chunk_data = {}
for chunk_hash, peer_list in chunks.items():
    peer = peer_list[0]  # Try first peer
    chunk_data[chunk_hash] = tcp_download(peer.ip, peer.port, chunk_hash)

# 4. Reconstruct file
reconstructed = merge_chunks(chunk_data)
save(reconstructed, "downloads/MPI.pdf")
```

---

## Configuration & Customization

### Port Assignments

| Component | Port | Purpose |
|-----------|------|---------|
| Node 1 DHT | 8468 | Kademlia DHT (bootstrap) |
| Node 1 Server | 9000 | TCP chunk serving |
| Node 2 DHT | 8469 | Kademlia DHT |
| Node 2 Server | 9001 | TCP chunk serving |
| Node 3 DHT | 8470 | Kademlia DHT |
| Node 3 Server | 9002 | TCP chunk serving |
| Client DHT | Random | Ephemeral DHT for download |

**Custom ports:**
```bash
python run_node.py --node-id custom-node --dht-port 8500 --serve-port 9500
```

### Erasure Coding Parameters

Edit `main.py` or node scripts to change:
- `k=4`: Number of data chunks
- `m=1`: Number of parity chunks
- Default chunk size: 65536 bytes (65KB)

File resilience: Can reconstruct even if m parity chunks + k-m data chunks are missing.

---

## Troubleshooting

### Issue: "File not found in network"

**Causes & Solutions:**
1. **No nodes running**: Ensure at least one node is running
   ```bash
   # Terminal 1: Node is up?
   python run_node1.py
   ```

2. **File not published**: Verify file exists in CAS index
   ```bash
   python main.py list
   ```

3. **DHT bootstrap failed**: Ensure bootstrap node (8468) is accessible
   - Node 1 must be running before starting Node 2/3
   - Ports must be available (check `netstat -an | find "9000"`)

4. **Wrong file hash**: Verify the FILE_HASH in download_file.py matches actual hash
   ```bash
   python main.py list  # Get correct hash
   ```

### Issue: "Connection refused" on TCP port 9000

**Solutions:**
1. Firewall blocking: Disable Windows Firewall for testing
   ```bash
   # Or allow Python in Windows Firewall
   ```

2. Port already in use:
   ```bash
   netstat -ano | findstr "9000"
   taskkill /PID <PID> /F
   ```

3. Node crashed: Check terminal for error messages, restart node

### Issue: DHT Timeout

**Solutions:**
1. Network timeout (multicast issue): Try again or restart node
2. Bootstrap node down: Start Node 1 first (8468 is bootstrap)
3. Multiple bootstrap attempts: Each retry waits 5 seconds

---

## Performance Tips

### For Fast Downloads:
1. **Multiple nodes**: More nodes = more parallel download sources
   ```bash
   # Start 5 nodes instead of 3
   python run_node1.py
   python run_node2.py
   python run_node3.py
   python run_node.py --node-id node4 --dht-port 8471 --serve-port 9003
   python run_node.py --node-id node5 --dht-port 8472 --serve-port 9004
   ```

2. **File replication**: Store same file on multiple nodes
   - Copy `storage/hashed_files/` chunks to different nodes

3. **Parallel downloads**: Increase `max_concurrent_downloads` in p2p_node.py

### For Production Deployment:
- Use dedicated bootstrap nodes
- Monitor DHT network health
- Implement chunk replication policy (store k copies minimum)
- Use Redis/database instead of in-memory DHT storage

---

## API Reference

### P2PNode
```python
from src.network.p2p_node import P2PNode

node = P2PNode(
    node_id="node1",
    server_host="127.0.0.1",
    server_port=9000,
    dht_port=8468,
    storage_dir="storage/hashed_files"
)

# Initialize
await node.initialize()

# Start serving
node.start_server()

# Download file
success = await node.download_file_from_peers(
    file_hash="ace997a024...",
    output_dir="downloads"
)

# Shutdown
await node.shutdown()
```

### P2PClient
```python
from src.network.p2p_client_new import P2PClient

client = P2PClient(
    dht_bootstrap_nodes=[("127.0.0.1", 8468)],
    download_dir="downloads"
)

await client.initialize()

# Download
success = await client.download_file("ace997a024...")

await client.shutdown()
```

### CAS (main.py)
```python
from src.cas.cas import CAS

cas = CAS(storage_dir="storage/hashed_files", chunk_size=65536)

# Store
file_hash = cas.store_file("myfile.txt")

# List
files = cas.list_files()

# Retrieve
cas.retrieve_file(file_hash, "output.txt")
```

---

## Network Flow Diagram

```
User wants to download "test.txt"
│
├─→ Client connects to DHT bootstrap node (127.0.0.1:8468)
│   └─→ DHT: "give me metadata for file_metadata:ace997a024..."
│       └─→ Returns: {original_name, chunks: [hash1, hash2...]}
│
├─→ For each chunk, query DHT
│   └─→ DHT: "give me peers for chunk hash1"
│       └─→ Returns: [{node_id: node1, ip: 127.0.0.1, port: 9000}]
│
├─→ Connect to peer TCP server (127.0.0.1:9000)
│   └─→ Send: GET_CHUNK hash1
│       ←─ Receive: 65536 bytes
│
├─→ Repeat for all chunks in parallel
│   └─→ Download from node1 (9000), node2 (9001), node3 (9002)
│
└─→ Merge chunks → Output file
    File reconstructed successfully!
```

---

## Summary of Commands

| Task | Command |
|------|---------|
| Start Node 1 | `python run_node1.py` |
| Start Node 2 | `python run_node2.py` |
| Start Node 3 | `python run_node3.py` |
| List stored files | `python main.py list` |
| Store new file | `python main.py store <file_path>` |
| Retrieve file locally | `python main.py retrieve <hash> <output>` |
| Download from network | `python download_file.py` (edit FILE_HASH first) |
| Interactive client | `python src/network/p2p_client_new.py` |
| Custom node | `python run_node.py --node-id <id> --dht-port <port> --serve-port <port>` |

---

## Next Steps

1. **Start 3 nodes** (Terminals 1-3)
2. **Try a download** (Terminal 4):
   ```bash
   python download_file.py
   ```
3. **Verify file** in `downloads/` directory
4. **Experiment**:
   - Stop Node 1, verify download still works from Node 2/3
   - Store new file, download it
   - Start more nodes, observe faster downloads
5. **Deploy to AWS** (see DEPLOYMENT_GUIDE.md for EC2/ECS instructions)

