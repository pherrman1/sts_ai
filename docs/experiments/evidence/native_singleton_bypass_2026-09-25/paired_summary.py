"""Paired singleton-bypass comparison on the standard 128-seed block.

Usage: python3 paired_summary.py  (run from this directory)
"""
import csv
import math
from pathlib import Path

here = Path(__file__).resolve().parent


def load(name):
    return {int(r["seed"]): r for r in csv.DictReader(open(here / name))}


a = load("control_126700_128.csv")
b = load("treatment_126700_128.csv")
assert set(a) == set(b) and len(a) == 128, "seed sets differ"
d = [int(b[s]["won"]) - int(a[s]["won"]) for s in sorted(a)]
m = sum(d) / len(d)
sd = (sum((x - m) ** 2 for x in d) / (len(d) - 1)) ** 0.5
se = sd / math.sqrt(len(d))
treatment_only = sum(1 for s in a if a[s]["won"] == "0" and b[s]["won"] == "1")
control_only = sum(1 for s in a if a[s]["won"] == "1" and b[s]["won"] == "0")
n = treatment_only + control_only
print(f"control (singleton roots searched) wins {sum(int(r['won']) for r in a.values())}/128, "
      f"treatment (unsearched) wins {sum(int(r['won']) for r in b.values())}/128")
print(f"paired difference {m * 100:+.1f} pp, normal 95% CI [{(m - 1.96 * se) * 100:+.1f}, {(m + 1.96 * se) * 100:+.1f}] pp")
print(f"discordant seeds: treatment-only {treatment_only}, control-only {control_only}, "
      f"McNemar z = {(treatment_only - control_only) / math.sqrt(n):+.2f}")
for key in ("floor", "sec"):
    print(f"mean {key}: control {sum(float(r[key]) for r in a.values()) / 128:.2f}, "
          f"treatment {sum(float(r[key]) for r in b.values()) / 128:.2f}")
