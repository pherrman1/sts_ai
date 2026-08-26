#!/usr/bin/env python3
"""Fail-fast validation for a fresh, small bestbench treatment canary.

The validator consumes artifacts already emitted by ``one_combat bestbench``.
It never drives game seeds. Use it after a guarded one-seed run and before
launching the remaining experimental cohort.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
from pathlib import Path


FAILURE_FIELDS = (
    "conversion_failures",
    "semantic_resolution_failures",
    "transaction_failures",
    "knowledge_failures",
)
SILVER_LINE = re.compile(r"^\[silver-combat\]\s+(?P<fields>.+)$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_single_meta(path: Path) -> dict:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(records) == 1, f"{path}: expected one fresh metadata record, found {len(records)}")
    return records[0]


def read_results(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    require(rows, f"{path}: no completed seed rows")
    require("seed" in rows[0] and "won" in rows[0], f"{path}: not a bestbench results CSV")
    return rows


def parse_silver_telemetry(path: Path) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SILVER_LINE.match(line.strip())
        if not match:
            continue
        fields: dict[str, int] = {}
        for token in match.group("fields").split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            try:
                fields[key] = int(value)
            except ValueError:
                continue
        rows.append(fields)
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(args: argparse.Namespace) -> str:
    meta = read_single_meta(args.meta)
    rows = read_results(args.results)
    config = meta.get("config", {})
    seed_block = meta.get("seedBlock", {})

    require(meta.get("objective") == "bestbench", "metadata objective is not bestbench")
    require(meta.get("nSeeds") == args.expect_seeds, "metadata nSeeds does not match the canary")
    require(meta.get("sims") == args.expect_sims, "metadata simulation budget does not match")
    if args.expect_asc is not None:
        require(meta.get("asc") == args.expect_asc, "metadata ascension does not match")
    if args.expect_threads is not None:
        require(meta.get("threads") == args.expect_threads, "metadata thread count does not match")
    if args.expect_fair:
        require(config.get("fairPlay") is True, "project-fair mode was not effective")
    if args.expect_searcher3:
        require(config.get("searcher3") is True, "Searcher3 configuration was not effective")
    require(seed_block.get("lo") == args.expect_seed_lo, "metadata seed-block start does not match")
    require(seed_block.get("hi") == args.expect_seed_lo + args.expect_seeds - 1,
            "metadata seed-block end does not match")
    require(len(rows) == args.expect_seeds, "completed result-row count does not match metadata")
    seeds = [int(row["seed"]) for row in rows]
    require(len(set(seeds)) == len(seeds), "result seeds are not unique")
    require(set(seeds) == set(range(args.expect_seed_lo, args.expect_seed_lo + args.expect_seeds)),
            "result seeds do not equal the requested seed block")
    require(config.get("effectiveCombatBackend") == args.expect_backend,
            f"effective combat backend is {config.get('effectiveCombatBackend')!r}, expected {args.expect_backend!r}")

    if args.expect_executable_sha:
        require(config.get("executableGitSha") == args.expect_executable_sha,
                "executable SHA does not match the frozen SHA")
    if args.expect_binary_sha256:
        require(args.binary is not None, "--expect-binary-sha256 requires --binary")
        require(sha256(args.binary) == args.expect_binary_sha256.lower(),
                "binary SHA-256 does not match the frozen executable")

    if args.expect_backend == "silver":
        require(config.get("stsSilverSearchEffective") is True,
                "Silver was requested but was not the effective backend")
        require(config.get("silverSearchEnabled") is True,
                "Silver live backend was not installed")
        require(bool(config.get("silverUpstreamSha")), "Silver upstream SHA is missing")
        if args.expect_silver_reuse_cap_mode:
            require(config.get("silverReuseCapMode") == args.expect_silver_reuse_cap_mode,
                    "effective Silver reuse-cap mode does not match")
        require(args.log is not None, "Silver canary requires --log for mechanism/failure telemetry")
        telemetry = parse_silver_telemetry(args.log)
        require(telemetry, "no [silver-combat] telemetry found; treatment activation is unproved")
        require(any(row.get("decisions", 0) > 0 and row.get("simulations", 0) > 0 for row in telemetry),
                "Silver telemetry contains no actual decisions/simulations")
        for field in FAILURE_FIELDS:
            require(all(row.get(field) == 0 for row in telemetry),
                    f"Silver telemetry reports nonzero or missing {field}")

    wins = sum(int(row["won"]) for row in rows)
    return (f"benchmark_canary PASS backend={args.expect_backend} seeds={len(rows)} "
            f"wins={wins} sims={args.expect_sims} seed_lo={args.expect_seed_lo}")


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        results = root / "canary.csv"
        meta = root / "canary.csv.meta.json"
        log = root / "canary.log"
        binary = root / "one_combat"
        results.write_text("seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n942000,1,51,3,20,80,0,-1,-1,1.0\n", encoding="utf-8")
        record = {
            "objective": "bestbench", "seedBlock": {"lo": 942000, "hi": 942000},
            "nSeeds": 1, "sims": 64, "asc": 0, "threads": 24,
            "config": {"effectiveCombatBackend": "silver", "stsSilverSearchEffective": True,
                       "silverSearchEnabled": True, "silverReuseCapMode": "active",
                       "silverUpstreamSha": "84ab3e", "executableGitSha": "deadbeef",
                       "fairPlay": True, "searcher3": True},
        }
        meta.write_text(json.dumps(record) + "\n", encoding="utf-8")
        log.write_text("[silver-combat] decisions=2 simulations=128 conversion_failures=0 semantic_resolution_failures=0 transaction_failures=0 knowledge_failures=0\n", encoding="utf-8")
        binary.write_bytes(b"frozen-binary")
        args = argparse.Namespace(results=results, meta=meta, log=log, expect_backend="silver",
                                  expect_seeds=1, expect_sims=64, expect_seed_lo=942000,
                                  expect_executable_sha="deadbeef", expect_silver_reuse_cap_mode="active",
                                  binary=binary, expect_binary_sha256=sha256(binary), expect_asc=0,
                                  expect_threads=24, expect_fair=True, expect_searcher3=True)
        validate(args)
        record["config"]["effectiveCombatBackend"] = "native_searcher"
        meta.write_text(json.dumps(record) + "\n", encoding="utf-8")
        try:
            validate(args)
        except ValueError as exc:
            require("effective combat backend" in str(exc), "wrong failure for bypassed treatment")
        else:
            raise AssertionError("bypassed Silver treatment was accepted")
    print("benchmark_canary self-test PASS")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--results", type=Path)
    p.add_argument("--meta", type=Path)
    p.add_argument("--log", type=Path)
    p.add_argument("--expect-backend", choices=("silver", "native_searcher"))
    p.add_argument("--expect-seeds", type=int, default=1)
    p.add_argument("--expect-sims", type=int)
    p.add_argument("--expect-seed-lo", type=int)
    p.add_argument("--expect-asc", type=int)
    p.add_argument("--expect-threads", type=int)
    p.add_argument("--expect-fair", action="store_true")
    p.add_argument("--expect-searcher3", action="store_true")
    p.add_argument("--expect-executable-sha")
    p.add_argument("--binary", type=Path)
    p.add_argument("--expect-binary-sha256")
    p.add_argument("--expect-silver-reuse-cap-mode", choices=("allocated", "active"))
    return p


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        return self_test()
    missing = [name for name in ("results", "meta", "expect_backend", "expect_sims", "expect_seed_lo")
               if getattr(args, name) is None]
    if missing:
        raise SystemExit("missing required canary arguments: " + ", ".join(missing))
    try:
        print(validate(args))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"benchmark_canary FAIL: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
