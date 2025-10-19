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
    return h


storage_dir = "cas_storage"
filepath = "testfiles/test.txt"  # Replace with your assigned file
file_hash = store_file(filepath, storage_dir)
print(f"Stored file with hash: {file_hash}")
