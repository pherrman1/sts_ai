#!/usr/bin/env python3
"""§104 Step-1-style label diagnostic for strategicgen2 Tier-B corpora.

For every decision group with a `chosen` row and labeled rows, compare the
argmax(labelWon) action against the chosen action:

- strict:  argmax(labelWon) == chosen action
- in-set:  chosen action is tied at the max labelWon (ties common: labelWon is
  the branch-fight win flag, mostly 0/1)

Reported overall and per screen (1=REST, 2=MAP, 3=EVENT, 4=REWARDS,
5=TREASURE, 6=SHOP, 7=BOSS_RELIC, 8=CARD_SELECT). Reference (old tierb corpus,
§104): 38.0% strict / 58.1% in-set.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

SCREENS = {
    1: "REST",
    2: "MAP",
    3: "EVENT",
    4: "REWARDS",
    5: "TREASURE",
    6: "SHOP",
    7: "BOSS_RELIC",
    8: "CARD_SELECT",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    args = parser.parse_args()

    import csv

    path = Path(args.csv)
    groups: dict[tuple[int, int], dict[str, list]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("labelWon", "") == "" or row.get("chosen", "") == "":
                continue
            key = (int(row["seed"]), int(row["decIdx"]))
            g = groups.setdefault(key, {"chosen_action": None, "screen": None, "lw": []})
            if row["chosen"] == "1":
                g["chosen_action"] = row["actionType"]
                g["screen"] = int(row["screen"])
            try:
                g["lw"].append((float(row["labelWon"]), row["actionType"]))
            except ValueError:
                continue

    strict = in_set = total = 0
    per_screen: dict[int, list[int]] = {}
    for g in groups.values():
        if g["chosen_action"] is None or not g["lw"]:
            continue
        best = max(lw for lw, _ in g["lw"])
        winners = {a for lw, a in g["lw"] if lw == best}
        total += 1
        if g["chosen_action"] in winners:
            in_set += 1
            if len(winners) == 1:
                strict += 1
        bucket = per_screen.setdefault(g["screen"], [0, 0, 0])
        bucket[0] += 1
        if g["chosen_action"] in winners:
            bucket[1] += 1
            if len(winners) == 1:
                bucket[2] += 1

    print(f"{path.name}: {total} decisions with chosen + labeled rows "
          f"({len(groups)} groups scanned)")
    print(f"overall strict {100.0 * strict / total:.1f}%  in-set "
          f"{100.0 * in_set / total:.1f}%  (n={total})")
    print("per screen (strict / in-set / n):")
    for screen in sorted(per_screen):
        n, s_in, s_strict = per_screen[screen]
        name = SCREENS.get(screen, f"screen{screen}")
        print(f"  {name:<12} {100.0 * s_strict / n:5.1f}%  {100.0 * s_in / n:5.1f}%  {n}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
