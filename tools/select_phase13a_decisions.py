#!/usr/bin/env python3
"""Deterministically freeze the Phase-13A eligible decision sample."""
import argparse
import csv
import hashlib
import random
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--sample-seed", type=int, default=1301)
    ap.add_argument("--count", type=int, default=16)
    args = ap.parse_args()

    with args.candidates.open(newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (int(r["sourceSeed"]), int(r["decisionId"])))
    if len(rows) < args.count:
        raise SystemExit(
            f"mechanism-starved: {len(rows)} eligible candidates, need {args.count}"
        )
    rng = random.Random(args.sample_seed)
    selected = sorted(
        rng.sample(rows, args.count),
        key=lambda r: (int(r["sourceSeed"]), int(r["decisionId"])),
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    digest = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    print(f"eligible={len(rows)} selected={len(selected)} sample_seed={args.sample_seed}")
    print(f"manifest={args.manifest} sha256={digest}")


if __name__ == "__main__":
    main()