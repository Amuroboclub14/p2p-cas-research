from src.cas import cas
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="SHA-256 File Hasher")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # store command (renamed from hash)
    store_parser = subparsers.add_parser("store", help="Store file using SHA-256 hash")
    store_parser.add_argument("file", help="Path to file to store")

    # when building subparsers:
    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve a file from CAS")
    retrieve_parser.add_argument("hash", help="Hash of file to retrieve")
    retrieve_parser.add_argument("output", help="Output file path")
    retrieve_parser.add_argument(
        "--force", action="store_true", help="Overwrite output file if it exists"
    )

    args = parser.parse_args()

    if args.command == "store":
        print(f"\nStoring file: {args.file}")
        storage_dir = "storage/hashed_files"
        file_hash = cas.store_file(args.file, storage_dir)
        print(f"File stored with hash:\n{file_hash}")
    elif args.command == "retrieve":
        try:
            success = cas.retrieve_file(args.hash, args.output, overwrite=args.force)
            if success:
                print(f"\n✓ File retrieved successfully: {args.output}")
                return 0
            else:
                print("\n✗ Failed to retrieve file")
                return 1
        except Exception as e:
            print(f"Error retrieving file: {e}")
            return 1
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
