"""Reuse seeded data or generate it without overwriting existing CSVs."""

import argparse
import json
from pathlib import Path

from generator.generate import generate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1000000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.out / "manifest.json"
    if manifest.exists():
        info = json.loads(manifest.read_text())
        if info["source_rows"] != args.rows or info["seed"] != 42:
            raise SystemExit("Existing dataset differs; choose a fresh DATA directory.")
        print(f"Reusing {args.rows:,} seeded source records in {args.out}")
    else:
        generate(args.out, args.rows, seed=42, days=30)


if __name__ == "__main__":
    main()
