#!/usr/bin/env python3
"""Prepare the independent search-seed inputs for current ledger §348."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_SNAPSHOT_SHA256 = (
    "ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae"
)
EXPECTED_FAILURES = {
    "12100014/9",
    "12100014/20",
    "12100029/25",
    "12100039/17",
    "12100039/24",
}
SEED_DOMAIN = "silver-rollout-cost-followup-20260925"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def derived_seed(domain: str, rep: str, row: dict) -> int:
    material = (
        f"{SEED_DOMAIN}/{domain}/{rep}/{row['case_id']}/"
        f"{row['benchmark_seed']}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--status-smoke", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if digest(args.snapshots) != EXPECTED_SNAPSHOT_SHA256:
        raise SystemExit("frozen DEV snapshot SHA-256 mismatch")
    snapshots = read_jsonl(args.snapshots)
    smoke = read_jsonl(args.status_smoke)
    if len(snapshots) != 64 or len(smoke) != 64:
        raise SystemExit("expected exactly 64 frozen snapshots and status rows")
    if len({row.get("case_id") for row in snapshots}) != 64:
        raise SystemExit("frozen snapshots contain duplicate case_id values")
    if len({row.get("case_id") for row in smoke}) != 64:
        raise SystemExit("status smoke contains duplicate case_id values")

    smoke_by_case = {row["case_id"]: row for row in smoke}
    snapshot_by_case = {row["case_id"]: row for row in snapshots}
    if smoke_by_case.keys() != snapshot_by_case.keys():
        raise SystemExit("status smoke root membership differs from frozen snapshots")
    failures = {
        case_id for case_id, row in smoke_by_case.items()
        if row.get("status") != "ok"
    }
    if failures != EXPECTED_FAILURES:
        raise SystemExit(f"status mask changed: {sorted(failures)}")
    eligible = [row for row in snapshots if smoke_by_case[row["case_id"]]["status"] == "ok"]
    if len(eligible) != 59:
        raise SystemExit(f"expected 59 status-eligible roots, found {len(eligible)}")

    all_seeds: dict[str, set[int]] = {}
    identity_seeds: dict[str, dict[str, int]] = {}
    for row in eligible:
        if "isolated_search_seed" in row:
            raise SystemExit(f"snapshot already has isolated_search_seed: {row['case_id']}")
        identities = {}
        for domain, reps in (("teacher", 3), ("arm", 4)):
            for index in range(1, reps + 1):
                rep = f"{index:02d}"
                identity = f"{domain}_{rep}"
                seed = derived_seed(domain, rep, row)
                identities[identity] = seed
                all_seeds.setdefault(identity, set()).add(seed)
        if len(set(identities.values())) != 7:
            raise SystemExit(f"derived identities collided for root {row['case_id']}")
        identity_seeds[row["case_id"]] = identities
    for identity, seeds in all_seeds.items():
        if len(seeds) != len(eligible):
            raise SystemExit(f"derived {identity} values collide across roots")

    args.out_dir.mkdir(parents=True, exist_ok=False)
    manifest = args.out_dir / "seed_manifest.tsv"
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        columns = ["case_id", "benchmark_seed"] + [
            f"{domain}_{index:02d}"
            for domain, reps in (("teacher", 3), ("arm", 4))
            for index in range(1, reps + 1)
        ]
        stream.write("\t".join(columns) + "\n")
        for row in eligible:
            values = [row["case_id"], str(row["benchmark_seed"]) ] + [
                str(identity_seeds[row["case_id"]][column])
                for column in columns[2:]
            ]
            stream.write("\t".join(values) + "\n")

    for domain, reps in (("teacher", 3), ("arm", 4)):
        for index in range(1, reps + 1):
            rep = f"{index:02d}"
            output = args.out_dir / f"{domain}_{rep}.jsonl"
            with output.open("w", encoding="utf-8", newline="") as stream:
                for row in eligible:
                    transformed = dict(row)
                    transformed["isolated_search_seed"] = identity_seeds[row["case_id"]][
                        f"{domain}_{rep}"
                    ]
                    stream.write(json.dumps(transformed, separators=(",", ":")) + "\n")
            print(f"input={output} rows={len(eligible)} sha256={digest(output)}")
    print(f"manifest={manifest} rows={len(eligible)} sha256={digest(manifest)}")


if __name__ == "__main__":
    main()
