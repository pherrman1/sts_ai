#!/usr/bin/env python3
"""Build act4-states.jsonl for silverazact4gen from extracted Act-4 CTM label worker tars.

usage: make_states.py OUT.jsonl DIR [DIR ...]   (DIR: an extracted worker tar; act4-*.jsonl[.gz] found recursively, aborted-* dirs skipped)

Keeps the rows silverazact4gen would use (runValid, one capture, no quarantine, act 4, A20, Shield + Spear (56) or
Heart (57)) from the frozen label run's source seeds 111160000-111169999 only (no smoke or superseded rows), fails on a duplicate (sourceSeed, fightIdx), sorts by (sourceSeed, fightIdx) and prints counts.
"""
import glob
import gzip
import json
import os
import sys


def rows(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def usable(r):
    g = r["predictorInput"]["globals"]
    return (r.get("runValid") is True and r.get("captureStatus") == "exactly_one" and r.get("quarantineReason") == ""
            and r.get("act") == 4 and g.get("ascension") == 20 and r.get("encounter") in (56, 57)
            and 111160000 <= r.get("sourceSeed", -1) <= 111169999)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    out, kept, seen, skipped = argv[1], [], set(), 0
    for d in argv[2:]:
        files = sorted(glob.glob(os.path.join(d, "**", "act4-*.jsonl"), recursive=True)
                       + glob.glob(os.path.join(d, "**", "act4-*.jsonl.gz"), recursive=True))
        for path in files:
            if "aborted" in os.path.relpath(path, d):
                continue   # a worker's aborted partial unit (kept next to its rerun)
            for r in rows(path):
                if not usable(r):
                    skipped += 1
                    continue
                k = (r["sourceSeed"], r["fightIdx"])
                if k in seen:
                    raise SystemExit(f"duplicate {k} in {path}")
                seen.add(k)
                kept.append(r)
    kept.sort(key=lambda r: (r["sourceSeed"], r["fightIdx"]))
    with open(out, "x") as f:
        for r in kept:
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
    enc = {56: 0, 57: 0}
    for r in kept:
        enc[r["encounter"]] += 1
    print(json.dumps({"states": len(kept), "shield_and_spear": enc[56], "heart": enc[57], "skipped": skipped,
                      "source_runs": len({r["sourceSeed"] for r in kept})}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
