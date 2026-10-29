#!/usr/bin/env python3
"""Phase-1 root list for the root-quality campaign (PREREG.md, frozen rule).

Reads the arm-A records of the §712 card-rule campaign (unit tars) and picks, for the first 144 seeds (128 + 16 spares) of
111387000-111387255 whose game has a card-reward root, one root uniformly by splitmix64(seed ^ 0x524f4f5451).
A card-reward root is a real decision by heart1_screen on a REWARDS state (screen 2) with offered cards at floor >= 1.
Usage: python3 -I select_roots.py UNITS_DIR [LOCAL_DIR ...] > roots.tsv   (seed, decisionIndex, floor, act, nRoots, cards)
The cards column is the §712 root's offer; the analysis keeps a probed root only if main's state at that index is a
card reward (main does not replay every §712 game bit-exactly), and uses the first 128 valid roots in seed order.
"""
import gzip, io, json, sys, tarfile
from pathlib import Path

MASK = (1 << 64) - 1


def splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)


def arm_a_rows(dirs, seed):
    for d in dirs:
        for tar in sorted(Path(d).glob(f"{seed}.*.tar")):
            with tarfile.open(tar) as t:
                for m in t.getmembers():
                    if m.name.endswith(f"/A-{seed}.jsonl.gz"):
                        data = gzip.decompress(t.extractfile(m).read()).decode()
                        return [json.loads(l) for l in data.splitlines() if l.strip()]
    return None


def card_roots(rows):
    states = {r["index"]: r for r in rows if r.get("type") == "state"}
    out = []
    for r in rows:
        if r.get("type") != "decision" or r.get("by") != "heart1_screen":
            continue
        s = states.get(r["stateIndex"])
        if s and s["screen"] == 2 and s["floor"] >= 1 and s["record"].get("cards_offered.cards"):
            out.append((r["decisionIndex"], s["floor"], s["act"], s["record"]["cards_offered.cards"]))
    return out


def main():
    dirs = sys.argv[1:]
    picked = 0
    print("seed\tdecisionIndex\tfloor\tact\tnRoots\tcards")
    for seed in range(111387000, 111387256):
        rows = arm_a_rows(dirs, seed)
        if rows is None:
            raise SystemExit(f"no arm-A record for {seed}")
        roots = card_roots(rows)
        if not roots:
            continue
        idx, floor, act, cards = roots[splitmix64(seed ^ 0x524F4F5451) % len(roots)]
        print(f"{seed}\t{idx}\t{floor}\t{act}\t{len(roots)}\t{','.join(map(str, cards))}")
        picked += 1
        if picked == 144:
            break
    if picked < 144:
        raise SystemExit(f"only {picked} seeds with card roots")


if __name__ == "__main__":
    main()
