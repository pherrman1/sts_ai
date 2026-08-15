#!/usr/bin/env python3
"""Analyze committed Phase-13A paired S/R evaluator rows."""
import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path)
    ap.add_argument("summary", type=Path)
    args = ap.parse_args()
    groups = defaultdict(list)
    with args.raw.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["valid"] == "1":
                row["utility"] = 10.0 * float(row["won"]) + float(row["hpEnd"])
            key = (row["sourceSeed"], row["decisionId"])
            groups[key].append(row)
    out = []
    for key in sorted(groups, key=lambda k: (int(k[0]), int(k[1]))):
        rows = groups[key]
        invalid = [r for r in rows if r["valid"] != "1"]
        # Reconstruct future-paired deltas explicitly; rows are four futures per arm.
        def deltas(ev: str, field: str):
            m = {int(r["future"]): float(r[field]) for r in rows
                 if r["valid"] == "1" and r["evaluator"] == ev and r["actionRole"] == "M"}
            v = {int(r["future"]): float(r[field]) for r in rows
                 if r["valid"] == "1" and r["evaluator"] == ev and r["actionRole"] == "V"}
            return [m[i] - v[i] for i in sorted(set(m) & set(v))]

        usable = not invalid and all(
            len(deltas(ev, "utility")) == 4 for ev in ("S", "R")
        )
        su = deltas("S", "utility") if usable else []
        ru = deltas("R", "utility") if usable else []
        rw = deltas("R", "won") if usable else []
        short_delta = statistics.mean(su) if su else float("nan")
        ref_delta = statistics.mean(ru) if ru else float("nan")
        ref_win = statistics.mean(rw) if rw else float("nan")
        model_delta = float(rows[0]["modelDelta"])
        out.append({
            "sourceSeed": key[0], "decisionId": key[1], "act": rows[0]["act"],
            "floor": rows[0]["floor"], "screen": rows[0]["screen"],
            "modelDelta": model_delta, "shortDelta": short_delta,
            "refDelta": ref_delta, "refWinDelta": ref_win,
            "shortSign": sign(short_delta) if usable else "invalid",
            "refSign": sign(ref_delta) if usable else "invalid",
            "m0ModelSign": sign(model_delta),
            "shortM0": sum(x > 0 for x in su), "shortTie": sum(x == 0 for x in su),
            "shortV4": sum(x < 0 for x in su), "refM0": sum(x > 0 for x in ru),
            "refTie": sum(x == 0 for x in ru), "refV4": sum(x < 0 for x in ru),
            "refFutureStd": statistics.stdev(ru) if len(ru) > 1 else "",
            "refFutureRange": max(ru) - min(ru) if ru else "",
            "invalidRows": len(invalid),
            "validRows": len(rows),
        })
    if len(out) != 16:
        raise SystemExit(f"expected 16 decisions, found {len(out)}")
    fields = list(out[0])
    with args.summary.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader(); w.writerows(out)
    valid_out = [r for r in out if r["invalidRows"] == 0]
    s_count = Counter(sign(float(r["shortDelta"])) for r in valid_out)
    r_count = Counter(sign(float(r["refDelta"])) for r in valid_out)
    sr = sum(sign(float(r["shortDelta"])) == sign(float(r["refDelta"])) != 0 for r in valid_out)
    mr = sum(sign(float(r["modelDelta"])) == sign(float(r["refDelta"])) != 0 for r in valid_out)
    mean_ref = statistics.mean(float(r["refDelta"]) for r in valid_out) if valid_out else float("nan")
    mean_win = statistics.mean(float(r["refWinDelta"]) for r in valid_out) if valid_out else float("nan")
    print(f"decisions={len(out)} valid_decisions={len(valid_out)} invalid_rows={sum(int(r['invalidRows']) for r in out)} "
          f"mean_refDelta={mean_ref:.6f} mean_refWinDelta={mean_win:.6f}")
    print(f"S_preference M0={s_count[1]} V4={s_count[-1]} tie={s_count[0]}")
    print(f"R_preference M0={r_count[1]} V4={r_count[-1]} tie={r_count[0]}")
    print(f"strict_sign_agreement short_ref={sr}/{len(valid_out)} model_ref={mr}/{len(valid_out)}")
    print("screen_counts " + " ".join(
        f"screen{screen}={sum(r['screen'] == screen for r in out)}"
        for screen in sorted({r['screen'] for r in out}, key=int)
    ))


if __name__ == "__main__":
    main()