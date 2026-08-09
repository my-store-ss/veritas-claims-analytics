
import argparse
from pathlib import Path
from src.pipeline import process_folder, export_wide

def main():
    parser = argparse.ArgumentParser(description="Veritas Claims Analytics pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--input", default="sample-data")
    run.add_argument("--db", default="data/claims.db")
    run.add_argument("--reset", action="store_true")

    wide = sub.add_parser("export-wide")
    wide.add_argument("--db", default="data/claims.db")
    wide.add_argument("--out", default="output/canonical_wide.csv")

    args = parser.parse_args()
    if args.command == "run":
        print(process_folder(args.input, args.db, reset=args.reset))
    elif args.command == "export-wide":
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        export_wide(args.db, args.out)
        print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
