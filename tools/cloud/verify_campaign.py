#!/usr/bin/env python3
"""Verify every worker delivery of a tools/cloud/worker.sh campaign in one pass.

For each worker W in 1..workers this checks that SHARE/wWW.tar and SHARE/wWW.DONE.json exist, that the tar's
sha256 equals DONE.json's tar_sha256, that DONE.json lists exactly the units units.txt assigns to W, and that the
tar holds a .done marker for each of them. It prints one line per worker and a summary, and exits 0 only when
every worker is OK. The facts come from the files, never from what a worker said in chat.

Usage: python3 tools/cloud/verify_campaign.py CAMPAIGN_DIR [--share DIR] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path


def read_manifest(path: Path) -> dict:
    keys: dict = {"input": []}
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "input":
            keys["input"].append(parts[1:])
        else:
            keys[parts[0]] = " ".join(parts[1:])
    return keys


def unit_lines(path: Path) -> list[str]:
    return [l.rstrip("\n") for l in path.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def unit_id(line: str) -> str:
    # Same mapping as worker.sh: tr -c 'A-Za-z0-9._-' '_'
    return re.sub(r"[^A-Za-z0-9._-]", "_", line)


def assigned(units: list[str], workers: int, w: int) -> list[str]:
    return [u for i, u in enumerate(units) if i % workers + 1 == w]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_worker(share: Path, units: list[str], workers: int, w: int) -> tuple[str, str]:
    tag = f"w{w:02d}"
    tar, done = share / f"{tag}.tar", share / f"{tag}.DONE.json"
    if not done.exists() or not tar.exists():
        return "MISSING", f"{'tar ' if not tar.exists() else ''}{'DONE.json' if not done.exists() else ''}".strip()
    try:
        meta = json.loads(done.read_text())
    except (OSError, ValueError) as e:
        return "BAD", f"DONE.json unreadable: {e}"
    want = assigned(units, workers, w)
    if meta.get("worker") != w:
        return "BAD", f"DONE.json says worker {meta.get('worker')}"
    if meta.get("units") != want:
        return "BAD", f"DONE.json lists {len(meta.get('units') or [])} units, units.txt assigns {len(want)}"
    got = sha256(tar)
    if got != meta.get("tar_sha256"):
        return "BAD", f"tar sha256 {got[:12]} != DONE.json {str(meta.get('tar_sha256'))[:12]}"
    try:
        with tarfile.open(tar) as t:
            names = set(t.getnames())
    except (OSError, tarfile.TarError) as e:
        return "BAD", f"tar unreadable: {e}"
    missing = [u for u in want if f"out/units/{unit_id(u)}.done" not in names]
    if missing:
        return "BAD", f"{len(missing)} unit markers missing, first: {missing[0]}"
    return "OK", f"{len(want)} units, tar {got[:12]}, {meta.get('finished_utc', '?')}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("campaign")
    ap.add_argument("--share", help="override the manifest's share dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    d = Path(a.campaign)
    m = read_manifest(d / "campaign.manifest")
    workers = int(m["workers"])
    share = Path(a.share or m["share"])
    units = unit_lines(d / "units.txt")
    rows = [(w, *check_worker(share, units, workers, w)) for w in range(1, workers + 1)]
    if a.json:
        print(json.dumps([{"worker": w, "state": s, "detail": x} for w, s, x in rows], indent=1))
    else:
        for w, s, x in rows:
            print(f"w{w:02d} {s:7s} {x}")
        for state in ("OK", "MISSING", "BAD"):
            ws = [str(w) for w, s, _ in rows if s == state]
            print(f"{state}: {' '.join(ws) if ws else '-'}")
    return 0 if all(s == "OK" for _, s, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
