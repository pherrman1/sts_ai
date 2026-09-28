"""Merge the per-offset shards into one row per seed (0..127) per arm.

The offset-32 shard files also contain copies of seeds 0..31: before phase 2
started, the 32-seed screen's merged file was written to the same name and
bestbench then appended the shard's seeds 32..35. The copies are asserted
byte-identical to the original rows and dropped.
"""
import csv
import sys

for arm in ("control", "shared"):
    rows = {}
    for off in range(0, 128, 4):
        for r in csv.reader(open(f"shards/{arm}_{off}.csv")):
            if r[0] == "seed":
                header = r
                continue
            s = int(r[0])
            if s in rows:
                assert rows[s] == r, (arm, s)
                continue
            rows[s] = r
    assert sorted(rows) == list(range(128)), arm
    with open(f"{arm}_128.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for s in range(128):
            w.writerow(rows[s])
