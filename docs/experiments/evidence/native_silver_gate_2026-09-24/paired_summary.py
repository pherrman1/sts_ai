"""Paired native-vs-vendored Silver comparison on the standard 128-seed block.

Usage: python3 paired_summary.py  (run from this directory)
"""
import csv
import math
from pathlib import Path

here = Path(__file__).resolve().parent
baseline = here.parent / "silver_handoff_timing_2026-09-24" / "bestbench_adaptive_126700_128.csv"
native = here / "bestbench_native_adaptive_126700_128.csv"


def load(path):
    return {int(r["seed"]): r for r in csv.DictReader(open(path))}


a, b = load(baseline), load(native)
assert set(a) == set(b) and len(a) == 128, "seed sets differ"
d = [int(b[s]["won"]) - int(a[s]["won"]) for s in sorted(a)]
m = sum(d) / len(d)
sd = (sum((x - m) ** 2 for x in d) / (len(d) - 1)) ** 0.5
se = sd / math.sqrt(len(d))
native_only = sum(1 for s in a if a[s]["won"] == "0" and b[s]["won"] == "1")
vendored_only = sum(1 for s in a if a[s]["won"] == "1" and b[s]["won"] == "0")
n = native_only + vendored_only
print(f"vendored wins {sum(int(r['won']) for r in a.values())}/128, "
      f"native wins {sum(int(r['won']) for r in b.values())}/128")
print(f"paired difference {m * 100:+.1f} pp, normal 95% CI [{(m - 1.96 * se) * 100:+.1f}, {(m + 1.96 * se) * 100:+.1f}] pp")
print(f"discordant seeds: native-only {native_only}, vendored-only {vendored_only}, "
      f"McNemar z = {(native_only - vendored_only) / math.sqrt(n):+.2f}")
print(f"mean floor vendored {sum(int(r['floor']) for r in a.values()) / 128:.2f}, "
      f"native {sum(int(r['floor']) for r in b.values()) / 128:.2f}")
