#!/usr/bin/env python3
"""Replay check: two bestbench runs on identical seeds must produce identical
per-seed rows.

Runs `./build/one_combat bestbench <sims> <nseeds> <asc> [seedOffset]` twice
into fresh CSV files and compares every column except `sec` (wall-clock
timing). Rows are aligned on `seed` because bestbench flushes rows in
completion order.

Usage: check_replay.py <sims> <nseeds> <asc> [seedOffset]
       check_replay.py --self-test
"""
import os
import subprocess
import sys
import tempfile

HEADER = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec"
COMPARE_COLS = [c for c in HEADER.split(",") if c not in ("seed", "sec")]


def parse_csv(text):
    rows = {}
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty CSV")
    hdr = [c.strip() for c in lines[0].split(",")]
    if hdr != HEADER.split(","):
        raise ValueError("unexpected header %r; expected %r" % (hdr, HEADER.split(",")))
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.split(",")]
        row = dict(zip(hdr, cells))
        rows[int(row["seed"])] = row
    return rows


def compare_rows(a, b):
    diffs = []
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    for seed in sorted(set(a) & set(b)):
        ra, rb = a[seed], b[seed]
        for col in COMPARE_COLS:
            if ra[col] != rb[col]:
                diffs.append((seed, col, ra[col], rb[col]))
    return diffs, only_a, only_b


def report(diffs, only_a, only_b):
    ok = True
    for col in COMPARE_COLS:
        cd = [d for d in diffs if d[1] == col]
        if cd:
            ok = False
            ex = ", ".join("seed%s %s->%s" % (d[0], d[2], d[3]) for d in cd[:3])
            print("FAIL %s: %d mismatch(es), e.g. %s" % (col, len(cd), ex))
        else:
            print("PASS %s" % col)
    if only_a or only_b:
        ok = False
        print("FAIL seed sets differ: only-in-A=%s only-in-B=%s" % (only_a, only_b))
    if ok:
        print("PASS: replay rows identical for every seed")
    return 0 if ok else 1


def self_test():
    good = HEADER + "\n0,1,12,3,45,80,2,0,5,1.23\n1,0,6,1,20,78,4,1,0,0.99\n"
    shuffled = HEADER + "\n1,0,6,1,20,78,4,1,0,0.31\n0,1,12,3,45,80,2,0,5,9.87\n"
    bad = HEADER + "\n0,1,12,3,46,80,2,0,5,1.23\n1,0,6,1,20,78,4,1,0,0.99\n2,1,3,1,10,70,3,0,1,0.50\n"
    diffs, only_a, only_b = compare_rows(parse_csv(good), parse_csv(shuffled))
    assert not diffs and not only_a and not only_b, (diffs, only_a, only_b)
    diffs, only_a, only_b = compare_rows(parse_csv(good), parse_csv(bad))
    assert any(d[1] == "hpEnd" for d in diffs), diffs
    assert not only_a and only_b == [2], (only_a, only_b)
    try:
        parse_csv("a,b,c\n1,2,3\n")
    except ValueError:
        pass
    else:
        raise AssertionError("parse_csv accepted an unknown header")
    print("self-test PASS: seed alignment, hpEnd mismatch and missing-seed detection verified")
    return 0


def main(argv):
    if argv and argv[0] == "--self-test":
        return self_test()
    if len(argv) < 3:
        print(__doc__)
        return 2
    sims, nseeds, asc = argv[0], argv[1], argv[2]
    seed_offset = argv[3] if len(argv) > 3 else "0"
    with tempfile.TemporaryDirectory() as td:
        out_a = os.path.join(td, "run_a.csv")
        out_b = os.path.join(td, "run_b.csv")
        base = ["./build/one_combat", "bestbench", sims, nseeds, asc, seed_offset]
        for out in (out_a, out_b):
            r = subprocess.run(base + [out], capture_output=True, text=True)
            if r.returncode != 0:
                print("check_replay: bestbench failed (exit %d): %s"
                      % (r.returncode, (r.stderr or r.stdout).strip()))
                return r.returncode or 1
        with open(out_a) as f:
            a = parse_csv(f.read())
        with open(out_b) as f:
            b = parse_csv(f.read())
    return report(*compare_rows(a, b))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
