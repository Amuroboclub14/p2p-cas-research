import hashlib, os, json

def hash_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def store_file(path, storage_dir):
    h = hash_file(path)
    outpath = os.path.join(storage_dir, h)
    if not os.path.exists(outpath):
        os.makedirs(storage_dir, exist_ok=True)
        with open(path, 'rb') as infile, open(outpath, 'wb') as outfile:
            outfile.write(infile.read())
        # Update index.json logic here
    return h
