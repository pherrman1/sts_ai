#!/usr/bin/env python3
"""Screening design of the Gumbel tuning experiment (PREREG.md): a 2^(10-5) fractional factorial of resolution IV.

Base factors A-E run the full 2^5 in standard order; F = ABCD, G = ABCE, H = ABDE, J = ACDE, K = BCDE
(Montgomery, Design and Analysis of Experiments, table of 2^(k-p) designs). The script checks the resolution
(shortest word of the defining relation has length 4) and that every main effect column is orthogonal to every
other main effect and to every two-factor interaction column (what resolution IV means).

usage: design.py [OUT.tsv]   (default: arms.tsv next to this script)
Columns: arm id, the 10 levels (-1/+1), the expertfights/selffights arm token string.
"""
import itertools
import os
import sys

FLAT = "flat16000"
# factor: (low token, high token); "" = the default (no token)
FACTORS = [
    ("A", "k", ("gsh8", "gsh32")),
    ("B", "c_scale", ("gcs0.5", "gcs2")),
    ("C", "noise", ("gnz0", "")),
    ("D", "halving", ("", "ghb")),
    ("E", "max_backup", ("mb2", "mb8")),
    ("F", "ucb", ("ucb12.5", "ucb50")),
    ("G", "prior_weight", ("pw100", "pw1600")),
    ("H", "tree_prior", ("tp2", "tp32")),
    ("J", "widen_end_turn", ("wet1.85", "wet7.4")),
    ("K", "widen_chance", ("wch1.85", "wch7.4")),
]
GENERATORS = {"F": "ABCD", "G": "ABCE", "H": "ABDE", "J": "ACDE", "K": "BCDE"}
CONTROL = "gsh16+flat16000+mb4"
GNR = "gsh16+flat16000+mb4+gnr"


def runs():
    base = "ABCDE"
    out = []
    for bits in itertools.product((-1, 1), repeat=5):
        lv = dict(zip(base, reversed(bits)))   # standard (Yates) order: A changes fastest
        for f, word in GENERATORS.items():
            x = 1
            for c in word:
                x *= lv[c]
            lv[f] = x
        out.append(lv)
    return out


def token(lv):
    parts = []
    for letter, _, (lo, hi) in FACTORS:
        t = hi if lv[letter] > 0 else lo
        if letter == "A":
            parts += [t, FLAT]
        elif t:
            parts.append(t)
    if "gsh" not in parts[0]:
        raise AssertionError("k token first")
    return "+".join(parts)


def check(design):
    letters = [f[0] for f in FACTORS]
    # defining relation: all products of the generator words I = <gen word><factor>
    words = [frozenset(GENERATORS[f] + f) for f in GENERATORS]
    relation = set()
    for r in range(1, len(words) + 1):
        for combo in itertools.combinations(words, r):
            w = frozenset()
            for x in combo:
                w = w ^ x
            relation.add(w)
    shortest = min(len(w) for w in relation)
    assert shortest == 4, f"resolution {shortest}"
    n = len(design)
    col = {c: [d[c] for d in design] for c in letters}
    for a in letters:
        assert sum(col[a]) == 0
        for b in letters:
            if a < b:
                assert sum(x * y for x, y in zip(col[a], col[b])) == 0, (a, b)
        for b, c in itertools.combinations(letters, 2):
            if a in (b, c):
                continue
            assert sum(x * y * z for x, y, z in zip(col[a], col[b], col[c])) == 0, (a, b, c)
    assert n == 32
    return shortest


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "arms.tsv")
    design = runs()
    res = check(design)
    letters = [f[0] for f in FACTORS]
    tokens = [token(d) for d in design]
    assert len(set(tokens)) == 32
    with open(out, "w") as f:
        f.write("# 2^(10-5) resolution %s; generators %s; factors %s\n" % (
            "IV" if res == 4 else res, " ".join(f"{k}={v}" for k, v in GENERATORS.items()),
            " ".join(f"{l}={n}:{lo or 'default'}/{hi or 'default'}" for l, n, (lo, hi) in FACTORS)))
        f.write("arm\t" + "\t".join(letters) + "\ttoken\n")
        for i, (d, t) in enumerate(zip(design, tokens), 1):
            f.write(f"d{i:02d}\t" + "\t".join(str(d[c]) for c in letters) + f"\t{t}\n")
        # The control on the coded scale: the log-scale centre of every two-level range except noise (1 = the
        # high level) and halving (equal = the low level).
        centre = {c: 0 for c in letters}
        centre.update({"C": 1, "D": -1})
        for arm, t in (("ctl", CONTROL), ("gnr", GNR)):
            f.write(arm + "\t" + "\t".join(str(centre[c]) for c in letters) + f"\t{t}\n")
        # Production (the scout's reference arm; not a Gumbel search, its levels are not on the design's scale).
        f.write("prod\t" + "\t".join("0" for _ in letters) + "\tprod\n")
    print(f"wrote {out}: 32 design arms + control + gnr, resolution IV")


if __name__ == "__main__":
    main()
