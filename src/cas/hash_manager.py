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
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
            chunk_hashes.append(hashlib.sha256(chunk).hexdigest())  
            read_so_far += len(chunk)
            percent = (read_so_far / total_size) * 100
            sys.stdout.write(f"\rHashing: {percent:.2f}%")
            sys.stdout.flush()

    print("\nDone.")
    return sha256.hexdigest(),chunk_hashes


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
    
    Args:
        path: Path to the file to store
        storage_dir: Directory where files and index will be stored
        chunk_size: Size of chunks for hashing (default: 65536 bytes)
    
    Returns:
        str: The SHA-256 hash of the stored file
    """
    # Hash file and get chunk hashes
    h, chunk_hashes = hash_file(path, chunk_size)
    outpath = os.path.join(storage_dir, h)
    
    # Create storage directory if it doesn't exist
    os.makedirs(storage_dir, exist_ok=True)
    
    # Load existing index
    index = load_index(storage_dir)
    
    # Store the file if it doesn't exist
    file_already_exists = os.path.exists(outpath)
    if not file_already_exists:
        with open(path, "rb") as infile, open(outpath, "wb") as outfile:
            outfile.write(infile.read())
        print(f"\n✓ Stored new file: {h}")
    else:
        print(f"\n✓ File already exists in storage: {h}")
    
    file_stat = os.stat(path) 
    original_name = os.path.basename(path)  
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    # Update or create metadata entry in dictionary
    if h in index:
        # File hash exists - update metadata
        names_list = index[h].get("names", [])
        if original_name not in names_list:
            names_list.append(original_name)
        
        index[h]["names"] = names_list
        index[h]["chunks"] = chunk_hashes           
        index[h]["chunk_count"] = len(chunk_hashes) 
        index[h]["chunk_size"] = chunk_size     
        index[h]["last_accessed"] = current_time    
        if "stored_at" not in index[h]:
            index[h]["stored_at"] = current_time    
        print(f"✓ Updated metadata for existing file")
    else:
        # New file - create complete metadata entry
        index[h] = {
            "hash": h,
            "original_name": original_name,
            "names": [original_name],
            "size": file_stat.st_size,
            "chunks": chunk_hashes,
            "chunk_count": len(chunk_hashes),
            "chunk_size": chunk_size,
            "stored_at": current_time,
            "last_accessed": current_time
        }
        print(f"✓ Created new metadata entry")
    
    # Save updated index
    save_index(storage_dir, index)
    print(f"✓ Metadata saved to: {os.path.join(storage_dir, 'cas_index.json')}")
    
    return h