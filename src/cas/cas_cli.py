from src.cas import hash_manager
import argparse


def main():
    parser = argparse.ArgumentParser(description="SHA-256 File Hasher")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    hash_parser = subparsers.add_parser("hash", help="Generate SHA256 hash of a file")

    parser.add_argument("file", help="Path to file to hash")

    args = parser.parse_args()

    if args.command == "store":
        print(f"\nStoring file: {args.file}")
        file_hash = hash_manager.store_file(args.file, args.storage_dir)
        print(f"File stored with hash:\n{file_hash}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
