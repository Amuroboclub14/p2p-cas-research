from src.cas import hash_manager
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="SHA-256 File Hasher")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # store command (renamed from hash)
    store_parser = subparsers.add_parser("store", help="Store file using SHA-256 hash")
    store_parser.add_argument("file", help="Path to file to store")

    args = parser.parse_args()

    if args.command == "store":
        print(f"\nStoring file: {args.file}")
        storage_dir = "cas_storage"
        file_hash = hash_manager.store_file(args.file, storage_dir)
        print(f"File stored with hash:\n{file_hash}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

