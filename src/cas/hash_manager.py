import hashlib, os, sys, json

# def hash_file(path):
#     with open(path, 'rb') as f:
#         return hashlib.sha256(f.read()).hexdigest()


def hash_file(filepath, chunk_size=65536):
    total_size = os.path.getsize(filepath)
    read_so_far = 0
    sha256 = hashlib.sha256()

    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
            read_so_far += len(chunk)
            percent = (read_so_far / total_size) * 100
            sys.stdout.write(f"\rHashing: {percent:.2f}%")
            sys.stdout.flush()

    print("\nDone.")
    return sha256.hexdigest()


def store_file(path, storage_dir):
    h = hash_file(path)
    outpath = os.path.join(storage_dir, h)
    if not os.path.exists(outpath):
        os.makedirs(storage_dir, exist_ok=True)
        with open(path, "rb") as infile, open(outpath, "wb") as outfile:
            outfile.write(infile.read())
        # Update index.json logic here

import datetime
from pathlib import Path

class IndexManager:
    def __init__(self, index_file="cas_index.json"):
        self.index_file = index_file
        self.index = self._load_index()
    
    def _load_index(self):
        """Load the index from JSON file, or create empty one if it doesn't exist"""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                print(f"Warning: Could not load index from {self.index_file}, creating new index")
                return {}
        return {}
    
    def _save_index(self):
        """Save the index to JSON file"""
        try:
            with open(self.index_file, 'w') as f:
                json.dump(self.index, f, indent=2)
        except IOError as e:
            print(f"Error saving index: {e}")
    
    def update_index(self, file_hash, metadata):
        """
        Update the index with file metadata
        
        Args:
            file_hash (str): The SHA-256 hash of the file
            metadata (dict): Dictionary containing file metadata
        """
        # Ensure required fields are present
        required_fields = ['original_filename', 'size']
        for field in required_fields:
            if field not in metadata:
                raise ValueError(f"Missing required metadata field: {field}")
        
        # Add timestamp if not provided
        if 'timestamp' not in metadata:
            metadata['timestamp'] = datetime.datetime.now().isoformat()
        
        # Add file_hash to metadata for consistency
        metadata['file_hash'] = file_hash
        
        # Update the index
        self.index[file_hash] = metadata
        self._save_index()
        
        print(f"Index updated for hash: {file_hash}")
        return True
    
    def get_file_metadata(self, file_hash):
        """Retrieve metadata for a given file hash"""
        return self.index.get(file_hash)
    
    def list_files(self):
        """List all files in the index"""
        return list(self.index.keys())
    
    def remove_file(self, file_hash):
        """Remove a file from the index"""
        if file_hash in self.index:
            del self.index[file_hash]
            self._save_index()
            return True
        return False

def hash_file(filepath, chunk_size=65536):
    """Calculate SHA-256 hash of a file with progress indication"""
    total_size = os.path.getsize(filepath)
    read_so_far = 0
    sha256 = hashlib.sha256()

    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
            read_so_far += len(chunk)
            percent = (read_so_far / total_size) * 100
            sys.stdout.write(f"\rHashing: {percent:.2f}%")
            sys.stdout.flush()

    print("\nDone.")
    return sha256.hexdigest()

def store_file(path, storage_dir):
    """Store file and update index with metadata"""
    # Initialize index manager
    index_manager = IndexManager()
    
    # Calculate hash
    h = hash_file(path)
    outpath = os.path.join(storage_dir, h)
    
    # Get file metadata
    file_stats = os.stat(path)
    original_filename = os.path.basename(path)
    
    metadata = {
        'original_filename': original_filename,
        'size': file_stats.st_size,
        'timestamp': datetime.datetime.now().isoformat(),
        'storage_path': outpath,
        'chunk_list': [],  # Empty for now, can be populated if chunking is implemented
        'file_extension': os.path.splitext(original_filename)[1],
        'last_modified': datetime.datetime.fromtimestamp(file_stats.st_mtime).isoformat()
    }
    
    # Store file if it doesn't exist
    if not os.path.exists(outpath):
        os.makedirs(storage_dir, exist_ok=True)
        with open(path, "rb") as infile, open(outpath, "wb") as outfile:
            outfile.write(infile.read())
        print(f"File stored at: {outpath}")
    else:
        print(f"File already exists in storage: {outpath}")
    
    # Update index
    index_manager.update_index(h, metadata)
    
    return h

# Global index manager instance
index_manager = IndexManager()


