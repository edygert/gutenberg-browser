import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gutenberg-browser",
        description="Browse and search Project Gutenberg metadata.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--update",
        action="store_true",
        help="Incrementally update the index from the current rdf-files.tar.zip, then open the browser.",
    )
    group.add_argument(
        "--reindex",
        action="store_true",
        help="Drop and fully rebuild the index from scratch, then open the browser.",
    )
    args = parser.parse_args()

    zip_path = Path("rdf-files.tar.zip")
    if not zip_path.exists():
        print(f"Error: {zip_path} not found. Run from the directory containing rdf-files.tar.zip.", file=sys.stderr)
        sys.exit(1)

    mode = "normal"
    if args.update:
        mode = "update"
    elif args.reindex:
        mode = "reindex"

    from .app import GutenbergApp
    app = GutenbergApp(mode=mode)
    app.run()


if __name__ == "__main__":
    main()
