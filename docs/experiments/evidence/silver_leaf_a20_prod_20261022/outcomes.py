#!/usr/bin/env python3
"""Run outcomes of a silverazgen campaign (README analysis step 4): Heart kill, Heart fights won and acts reached per
variant, from the fight rows of the unit tars (a run's rows are deduplicated by fight index, so a unit uploaded twice
counts once).

usage: outcomes.py UNIT_TAR...
"""
import collections
import concurrent.futures
import gzip
import json
import math
import sys
import tarfile


def fight_rows(path):
    rows = []
    with tarfile.open(path) as t:
        for m in t.getmembers():
            if m.name.endswith(".jsonl.gz"):
                for line in gzip.decompress(t.extractfile(m).read()).splitlines():
                    if b'"kind":"fight"' in line:
                        r = json.loads(line)
                        rows.append({k: r.get(k) for k in ("variant", "seed", "fight", "act", "encounter", "won",
                                                           "valid")})
    return rows


def wilson(k, n, z=1.96):
    p = k / n
    d, c = 1 + z * z / n, p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h) / d, 100 * (c + h) / d


runs = collections.defaultdict(dict)
with concurrent.futures.ThreadPoolExecutor(8) as ex:
    for rows in ex.map(fight_rows, sys.argv[1:]):
        for r in rows:
            runs[(r["variant"], r["seed"])][r["fight"]] = r
for var in ("natural", "perturbed"):
    rs = [sorted(f.values(), key=lambda x: x["fight"]) for (v, _), f in runs.items() if v == var]
    n = len(rs)
    if not n:
        continue
    reach = {a: sum(any(x["act"] >= a for x in f) for f in rs) for a in (2, 3, 4)}
    heart = sum(f[-1]["act"] == 4 and f[-1]["won"] and "HEART" in str(f[-1]["encounter"]) for f in rs)
    heart_fights = sum(any("HEART" in str(x["encounter"]) for x in f) for f in rs)
    invalid = sum(any(not x.get("valid", True) for x in f) for f in rs)
    lo, hi = wilson(heart, n)
    print(f"{var}: runs {n}, fights {sum(len(f) for f in rs)}, Heart killed {heart} ({100 * heart / n:.1f}%, 95% CI "
          f"{lo:.1f}-{hi:.1f}), Heart fights {heart_fights} (won {100 * heart / max(1, heart_fights):.1f}%), act 2 "
          f"reached {100 * reach[2] / n:.1f}%, act 3 {100 * reach[3] / n:.1f}%, act 4 {100 * reach[4] / n:.1f}%; "
          f"runs with an invalid fight {invalid}")
