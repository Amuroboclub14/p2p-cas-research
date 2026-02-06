#!/usr/bin/env python3
"""
Download a file from P2P network

Usage:
    python download_file.py <file_hash> [download_dir]
    
Examples:
    python download_file.py ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28
    python download_file.py ace997a024ffc93ccb685846ab1fa00d99558bebd211d289bd02aba6a2252b28 my_downloads
    
To get file hash:
    python main.py list
"""

import asyncio
import sys
from src.network.p2p_client_new import P2PClient


async def main():
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n✗ Error: Missing file hash argument")
        print("Usage: python download_file.py <file_hash> [download_dir]")
        sys.exit(1)
    
    file_hash = sys.argv[1]
    download_dir = sys.argv[2] if len(sys.argv) > 2 else "downloads"
    
    # Validate file hash format (should be 64 hex chars for SHA-256)
    if len(file_hash) != 64 or not all(c in '0123456789abcdef' for c in file_hash.lower()):
        print(f"✗ Error: Invalid file hash format")
        print(f"Expected 64-character hex string, got: {file_hash}")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("P2P File Downloader")
    print("="*60)
    print(f"File Hash: {file_hash}")
    print(f"Download Dir: {download_dir}")
    print("="*60 + "\n")
    
    client = P2PClient(
        dht_bootstrap_nodes=[('127.0.0.1', 8468)],
        download_dir=download_dir
    )
    
    print("[CLIENT] Connecting to network...")
    await client.initialize()
    
    print(f"[CLIENT] Downloading file: {file_hash[:16]}...")
    success = await client.download_file(file_hash)
    
    if success:
        print(f"\n✓ File downloaded to: {download_dir}/")
    else:
        print("\n✗ Download failed")
    
    await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
