import hashlib, os, sys, json
from datetime import datetime

# def hash_file(path):
#     with open(path, 'rb') as f:
#         return hashlib.sha256(f.read()).hexdigest()


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


"""def store_file(path, storage_dir):
    h = hash_file(path)
    outpath = os.path.join(storage_dir, h)
    if not os.path.exists(outpath):
        os.makedirs(storage_dir, exist_ok=True)
        with open(path, "rb") as infile, open(outpath, "wb") as outfile:
            outfile.write(infile.read())
        # Update index.json logic here"""


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
    """
    Store file in CAS and maintain metadata in cas_index.json
    Includes deduplication to avoid storing duplicate chunks.
    """
    # Hash file and get chunk hashes
    h, chunk_hashes, chunks_data = hash_file(path, chunk_size)
    outpath = os.path.join(storage_dir, h)

    os.makedirs(storage_dir, exist_ok=True)

    # Load existing metadata index
    index = load_index(storage_dir)

    # Check if file already exists
    file_already_exists = os.path.exists(outpath)
    if not file_already_exists:
        print(f"\n✓ Storing new file: {h}")
    else:
        print(f"\n✓ File already exists in storage: {h}")

    # --- 🧠 Deduplication logic starts here ---
    skipped_chunks = 0
    new_chunks = 0

    for chunk_hash, chunk_data in chunks_data:
        chunk_path = os.path.join(storage_dir, chunk_hash)

        # ✅ If this chunk already exists, skip storing it again
        if os.path.exists(chunk_path):
            skipped_chunks += 1
            continue  # don’t rewrite the same chunk

        # ✅ Otherwise, save the chunk
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
        new_chunks += 1

    print(f"✓ Stored {new_chunks} new chunks, skipped {skipped_chunks} existing chunks")
    # --- 🧠 Deduplication logic ends here ---

    # Gather file stats for metadata
    file_stat = os.stat(path)
    original_name = os.path.basename(path)
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    # --- Update or create metadata entry ---
    if h in index:
        names_list = index[h].get("names", [])
        if original_name not in names_list:
            names_list.append(original_name)

        index[h].update(
            {
                "names": names_list,
                "chunks": chunk_hashes,
                "chunk_count": len(chunk_hashes),
                "chunk_size": chunk_size,
                "last_accessed": current_time,
            }
        )
        if "stored_at" not in index[h]:
            index[h]["stored_at"] = current_time
        print(f"✓ Updated metadata for existing file")

    else:
        index[h] = {
            "hash": h,
            "original_name": original_name,
            "names": [original_name],
            "size": file_stat.st_size,
            "chunks": chunk_hashes,
            "chunk_count": len(chunk_hashes),
            "chunk_size": chunk_size,
            "stored_at": current_time,
            "last_accessed": current_time,
        }
        print(f"✓ Created new metadata entry")

    # Save updated metadata
    save_index(storage_dir, index)
    print(f"✓ Metadata saved to: {os.path.join(storage_dir, 'cas_index.json')}")

    return h


import os
import shutil
from datetime import datetime


def retrieve_file(
    file_hash: str,
    output_path: str,
    storage_dir: str = "storage/hashed_files",
    overwrite: bool = False,
    chunk_size: int = 65536,
) -> bool:

    # load index from storage_dir
    index = load_index(storage_dir)

    if file_hash not in index:
        print(f"✗ File not found in CAS index: {file_hash}")
        return False

    metadata = index[file_hash]
    print(f"Retrieving file: {metadata.get('original_name', '<unknown>')}")
    print(f"  Hash: {file_hash}")
    print(f"  Size: {metadata.get('size', '<unknown>')} bytes")
    print(f"  Chunks: {metadata.get('chunk_count', len(metadata.get('chunks', [])))}")

    # Ensure target dir exists
    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Overwrite safety
    if os.path.exists(output_path) and not overwrite:
        print(f"✗ Output file already exists: {output_path} (use --force to overwrite)")
        return False

    # Create temp file in same dir for atomic replace
    tmp_path = os.path.join(
        out_dir, f".{os.path.basename(output_path)}.tmp-{os.getpid()}"
    )

    try:
        with open(tmp_path, "wb") as out_f:
            for i, chunk_hash in enumerate(metadata["chunks"]):
                # chunk files are stored under storage_dir with filename = chunk_hash
                chunk_path = os.path.join(storage_dir, chunk_hash)

                if not os.path.exists(chunk_path):
                    print(f"✗ Missing chunk {i}: {chunk_hash}")
                    # cleanup
                    out_f.close()
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                    return False

                # stream the chunk file into output (low memory)
                with open(chunk_path, "rb") as chunk_f:
                    while True:
                        data = chunk_f.read(chunk_size)
                        if not data:
                            break
                        out_f.write(data)

                print(f"  ✓ Assembled chunk {i+1}/{len(metadata['chunks'])}")

            # flush and sync to disk
            out_f.flush()
            try:
                os.fsync(out_f.fileno())
            except OSError:
                # not fatal on some filesystems
                pass

        # move tmp to final destination (atomic on same FS)
        try:
            shutil.move(tmp_path, output_path)
        except Exception as e:
            print(f"✗ Failed to move temp file into place: {e}")
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return False

    except IOError as e:
        print(f"✗ I/O error while writing output: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"✗ Unexpected error during retrieval: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False

    # verify integrity using your hash_file (which returns (hash, chunk_hashes, chunks_data))
    print("Verifying file integrity...")
    try:
        reconstructed_hash = hash_file(output_path, chunk_size)[0]
    except Exception as e:
        print(f"✗ Error hashing reconstructed file: {e}")
        try:
            os.remove(output_path)
        except Exception:
            pass
        return False

    if reconstructed_hash == file_hash:
        print("✓ File integrity verified!")
        # update last_accessed in index and save
        index[file_hash]["last_accessed"] = datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3]
        save_index(storage_dir, index)
        return True
    else:
        print("✗ File integrity check failed!")
        print(f"  Expected: {file_hash}")
        print(f"  Got:      {reconstructed_hash}")
        try:
            os.remove(output_path)
        except Exception:
            pass
        return False
