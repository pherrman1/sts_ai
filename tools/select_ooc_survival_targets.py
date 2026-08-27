#!/usr/bin/env python3
"""Select targeted marginal OOC safety-vs-strength action pairs."""

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


DECISION = ("seed", "decIdx", "act", "floor", "screen")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_csv")
    ap.add_argument("out_csv")
    ap.add_argument("--raw-extra", action="append", default=[])
    ap.add_argument("--replicates", type=int, required=True)
    args = ap.parse_args()

    grouped = defaultdict(list)
    for raw_path in [args.raw_csv] + args.raw_extra:
        with open(raw_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = set(DECISION) | {"regime", "actionIdx", "actionBits",
                                        "survivedH", "continuationValue",
                                        "continuationSeed", "hiddenSeed"}
            missing = required - set(reader.fieldnames or ())
            if missing:
                raise SystemExit(f"missing columns in {raw_path}: {sorted(missing)}")
            for row in reader:
                if row["regime"] != "marg":
                    continue
                key = tuple(int(row[x]) for x in DECISION) + (int(row["actionIdx"]),)
                grouped[key].append(row)

    decisions = defaultdict(list)
    for key, rows in grouped.items():
        if len(rows) != args.replicates:
            raise SystemExit(f"incomplete replicate group {key}: {len(rows)}")
        replicate_keys = {(int(r["continuationSeed"]), int(r["hiddenSeed"]))
                          for r in rows}
        if len(replicate_keys) != args.replicates:
            raise SystemExit(f"duplicate marginal replicate key in {key}")
        bits = {int(r["actionBits"]) for r in rows}
        if len(bits) != 1:
            raise SystemExit(f"inconsistent actionBits in {key}")
        alive = [int(r["survivedH"]) for r in rows]
        if any(i not in (0, 1) for i in alive):
            raise SystemExit(f"non-binary survivedH in {key}")
        values = [float(r["continuationValue"]) for r in rows]
        if not all(math.isfinite(v) for v in values):
            raise SystemExit(f"non-finite continuationValue in {key}")
        n_alive = sum(alive)
        decisions[key[:-1]].append({
            "actionIdx": key[-1],
            "actionBits": bits.pop(),
            "replicateKeys": replicate_keys,
            "pSurvive": n_alive / len(rows),
            "vAlive": (sum(v for i, v in zip(alive, values) if i) / n_alive
                       if n_alive else 0.0),
        })

    selected = []
    for dkey, actions in sorted(decisions.items()):
        expected_keys = actions[0]["replicateKeys"]
        if any(a["replicateKeys"] != expected_keys for a in actions[1:]):
            raise SystemExit(f"sibling marginal CRN mismatch in {dkey}")
        candidates = []
        for i, a in enumerate(actions):
            for b in actions[i + 1:]:
                if ((a["pSurvive"] - b["pSurvive"])
                        * (a["vAlive"] - b["vAlive"]) >= -1e-12):
                    continue
                safe, strength = ((a, b) if a["pSurvive"] > b["pSurvive"]
                                  else (b, a))
                candidates.append((safe["pSurvive"] - strength["pSurvive"],
                                   strength["vAlive"] - safe["vAlive"],
                                   -safe["actionIdx"], -strength["actionIdx"],
                                   safe, strength))
        if not candidates:
            continue
        _, _, _, _, safe, strength = max(candidates)
        row = dict(zip(DECISION, dkey))
        row.update({"safeBits": safe["actionBits"],
                    "strengthBits": strength["actionBits"],
                    "safePSurvive": safe["pSurvive"],
                    "strengthPSurvive": strength["pSurvive"],
                    "safeVAlive": safe["vAlive"],
                    "strengthVAlive": strength["vAlive"],
                    "survivalDifference": safe["pSurvive"] - strength["pSurvive"],
                    "survivorValueDifference": strength["vAlive"] - safe["vAlive"]})
        selected.append(row)

    if not selected:
        raise SystemExit("no marginal safety-vs-strength targets found")
    fields = list(selected[0])
    out = Path(args.out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(selected)
    print(f"selected {len(selected)} marginal safety-vs-strength targets -> {out}")


if __name__ == "__main__":
    main()
