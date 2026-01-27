k = 4  #number of data chunks
m = 1  #number of parity chunks
import hashlib, os, sys, json, shutil
from datetime import datetime

def hash_file(filepath, chunk_size=65536):
    total_size = os.path.getsize(filepath)
    read_so_far = 0
    sha256 = hashlib.sha256()
    chunk_hashes = []
    chunks_data = []
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
            chunk_hash = hashlib.sha256(chunk).hexdigest()
            chunk_hashes.append(chunk_hash)
            chunks_data.append((chunk_hash, chunk))
            read_so_far += len(chunk)
            percent = (read_so_far / total_size) * 100
            sys.stdout.write(f"\rHashing: {percent:.2f}%")
            sys.stdout.flush()

    print("\nDone.")
    return sha256.hexdigest(), chunk_hashes, chunks_data

def save_index(storage_dir, index_data):
    """Save the index data to cas_index.json"""
    index_path = os.path.join(storage_dir, "cas_index.json")
    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2)


def load_index(storage_dir):
    index_path = os.path.join(storage_dir, "cas_index.json")
    if os.path.exists(index_path):
        try:
            with open(index_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: cas_index.json is corrupted. Creating new index.")
            return {}
    return {}


def store_file(path, storage_dir, chunk_size=65536):
    h, chunk_hashes, chunks_data = hash_file(path, chunk_size)

    os.makedirs(storage_dir, exist_ok=True)

    k = 4
    m = 1

    # counters FIRST
    new_chunks = 0
    skipped_chunks = 0

    # extract raw chunks
    data_chunks = [chunk_data for (_, chunk_data) in chunks_data]
    
    



    # XOR parity - pad chunks to consistent size for correct XOR
    parity_chunks = []
    max_chunk_size = len(data_chunks[0]) if data_chunks else 0
    for _ in range(m):
        parity = bytearray(max_chunk_size)
        for chunk in data_chunks:
            # Pad chunk if smaller than max (last chunk may be smaller)
            padded_chunk = chunk + b'\x00' * (max_chunk_size - len(chunk))
            for i in range(max_chunk_size):
                parity[i] ^= padded_chunk[i]
        parity_chunks.append(bytes(parity))

    # saving data chunks
    data_chunk_hashes = []
    for chunk in data_chunks:
        ch = hashlib.sha256(chunk).hexdigest()
        data_chunk_hashes.append(ch)

        chunk_path = os.path.join(storage_dir, ch)
        if not os.path.exists(chunk_path):
            with open(chunk_path, "wb") as f:
                f.write(chunk)
            new_chunks += 1
        else:
            skipped_chunks += 1

    # saving parity chunks
    parity_chunk_hashes = []
    for chunk in parity_chunks:
        ch = hashlib.sha256(chunk).hexdigest()
        parity_chunk_hashes.append(ch)

        chunk_path = os.path.join(storage_dir, ch)
        if not os.path.exists(chunk_path):
            with open(chunk_path, "wb") as f:
                f.write(chunk)
            new_chunks += 1
        else:
            skipped_chunks += 1

    print(f"✓ Stored {new_chunks} new chunks, skipped {skipped_chunks} existing chunks")

    # metadata
    index = load_index(storage_dir)

    file_stat = os.stat(path)
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    index[h] = {
        "hash": h,
        "original_name": os.path.basename(path),
        "size": file_stat.st_size,
        "k": k,
        "m": m,
        "data_chunks": data_chunk_hashes,
        "parity_chunks": parity_chunk_hashes,
        "chunk_size": chunk_size,
        "stored_at": current_time,
        "last_accessed": current_time,
    }

    save_index(storage_dir, index)
    print(f"✓ Metadata saved to {storage_dir}/cas_index.json")

    return h



def retrieve_file(
    file_hash: str,
    output_path: str,
    storage_dir: str = "storage/hashed_files",
    overwrite: bool = False,
    chunk_size: int = 65536,
) -> bool:
    """
    Retrieve a file from CAS storage by its hash.
    Supports reconstruction of one missing data chunk using XOR parity.
    """
    index = load_index(storage_dir)

    if file_hash not in index:
        print(f"✗ File not found in CAS index: {file_hash}")
        return False

    metadata = index[file_hash]
    original_size = metadata.get("size", 0)
    print(f"Retrieving file: {metadata.get('original_name', '<unknown>')}")
    print(f"  Hash: {file_hash}")
    print(f"  Size: {original_size} bytes")

    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(output_path) and not overwrite:
        print(f"✗ Output file already exists: {output_path}")
        return False

    tmp_path = os.path.join(
        out_dir, f".{os.path.basename(output_path)}.tmp-{os.getpid()}"
    )

    try:
        data_chunk_hashes = metadata["data_chunks"]
        parity_chunk_hashes = metadata["parity_chunks"]
        stored_chunk_size = metadata.get("chunk_size", chunk_size)

        # Load all data chunks, tracking missing ones
        chunks = []
        missing_indices = []

        for i, ch in enumerate(data_chunk_hashes):
            chunk_path = os.path.join(storage_dir, ch)
            if os.path.exists(chunk_path):
                with open(chunk_path, "rb") as f:
                    chunks.append(f.read())
            else:
                print(f"  ⚠ Missing data chunk {i}: {ch[:16]}...")
                missing_indices.append(i)
                chunks.append(None)

        # Check how many chunks are missing
        if len(missing_indices) > 1:
            print(f"✗ Too many missing chunks ({len(missing_indices)}). XOR parity can only recover 1.")
            return False

        # Reconstruct missing chunk if exactly one is missing
        if len(missing_indices) == 1:
            missing_idx = missing_indices[0]
            print(f"  → Attempting to reconstruct chunk {missing_idx} using parity...")

            if not parity_chunk_hashes:
                print("✗ No parity chunks available for reconstruction.")
                return False

            parity_path = os.path.join(storage_dir, parity_chunk_hashes[0])
            if not os.path.exists(parity_path):
                print("✗ Parity chunk missing, cannot reconstruct the file.")
                return False

            # Load parity chunk
            with open(parity_path, "rb") as pf:
                parity_data = bytearray(pf.read())

            # XOR all available chunks with parity to recover missing chunk
            recovered = parity_data  # Start with parity
            for i, chunk in enumerate(chunks):
                if chunk is not None:
                    # Pad chunk to match parity size if needed (last chunk may be smaller)
                    padded_chunk = chunk + b'\x00' * (len(recovered) - len(chunk))
                    for j in range(len(recovered)):
                        recovered[j] ^= padded_chunk[j]

            # Insert recovered chunk (may need to trim if it was the last chunk)
            chunks[missing_idx] = bytes(recovered)
            print(f"  ✓ Chunk {missing_idx} reconstructed successfully.")

        # Write all chunks to output file
        with open(tmp_path, "wb") as out_f:
            for chunk in chunks:
                if chunk is not None:
                    out_f.write(chunk)

        # Truncate to original file size (removes padding from last chunk)
        if original_size > 0:
            with open(tmp_path, "r+b") as f:
                f.truncate(original_size)

        # Atomically move temp file to final location
        os.replace(tmp_path, output_path)

    except Exception as e:
        print(f"✗ Error during retrieval: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

    # Verify file integrity
    print("Verifying file integrity...")
    reconstructed_hash = hash_file(output_path, chunk_size)[0]

    if reconstructed_hash == file_hash:
        print("✓ File integrity verified!")
        return True
    else:
        print("✗ File integrity check failed!")
        print(f"  Expected: {file_hash}")
        print(f"  Got:      {reconstructed_hash}")
        os.remove(output_path)
        return False
            

def list_files(storage_dir="storage/hashed_files"):
    """
    List all files stored in CAS using cas_index.json
    """
    index = load_index(storage_dir)

    if not index:
        print("No files stored in CAS.")
        return

    print("\nStored Files in CAS:")
    print("-" * 60)

    for file_hash, metadata in index.items():
        name = metadata.get("original_name", "<unknown>")
        size = metadata.get("size", 0)
        chunk_count = metadata["k"] + metadata["m"]
        stored_at = metadata.get("stored_at", "<unknown>")
        last_accessed = metadata.get("last_accessed", "<unknown>")

        print(f"File: {name}")
        print(f" Hash:          {file_hash}")
        print(f" Size:          {size} bytes")
        print(f" Chunks:        {chunk_count}")
        print(f" Stored At:     {stored_at}")
        print(f" Last Accessed: {last_accessed}")
        print("-" * 60)

def verify_integrity(storage_dir, file_hash):
    """
    Verify integrity of a single file:
    - Loads cas_index.json
    - Checks if all chunks of the given file_hash exist
    - Returns True/False
    """

    print(f"Verifying integrity for file hash: {file_hash}")

    index = load_index(storage_dir)

    # file_hash not found in index
    if file_hash not in index:
        print("✗ File hash not found in index.")
        return None

    metadata = index[file_hash]
    chunk_hashes = metadata["data_chunks"] + metadata["parity_chunks"]

    print(f"File: {metadata['original_name']}")
    missing_chunks = []

    # check each chunk
    for chunk_hash in chunk_hashes:
        chunk_path = os.path.join(storage_dir, chunk_hash)

        if not os.path.exists(chunk_path):
            missing_chunks.append(chunk_hash)

    # print results
    if missing_chunks:
        print(f"✗ Missing chunks: {missing_chunks}")
        return False
    else:
        print("✓ All chunks present.")
        return True

