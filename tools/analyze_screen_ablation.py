#!/usr/bin/env python3
"""Summarize paired per-screen OOC ablation CSVs.

The harness writes one full-stack CSV and ``screen_no_<screen>...csv`` files.
This tool pairs by seed through paired_analysis.py and reports the isolated
screen contribution as (full - ablation).
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paired_analysis

SCREENS = ("rest", "event", "shop", "treasure", "boss")


def _load(path):
    rows, _ = paired_analysis.load(path)
    return {r["seed"]: r for r in rows}


def summarize(full_path, outdir, screens=SCREENS, suffix="1k_128.csv"):
    full = _load(full_path)
    result = []
    for screen in screens:
        path = os.path.join(outdir, f"screen_no_{screen}_{suffix}")
        if not os.path.exists(path):
            continue
        ablated = _load(path)
        seeds = sorted(set(full) & set(ablated))
        if set(full) != set(ablated):
            raise ValueError(f"{path}: seed set differs from full arm")
        win_delta = sum(full[s]["won"] - ablated[s]["won"] for s in seeds) / len(seeds)
        floor_delta = sum(full[s]["floor"] - ablated[s]["floor"] for s in seeds) / len(seeds)
        hp_delta = sum(full[s]["hp"] - ablated[s]["hp"] for s in seeds) / len(seeds)
        result.append({"screen": screen, "n": len(seeds),
                       "win_delta_pp": 100.0 * win_delta,
                       "floor_delta": floor_delta, "hp_delta": hp_delta,
                       "paired_file": path})
    return result


def render(rows):
    lines = ["screen                  n   full-minus-ablation win pp   floor     hp"]
    for r in rows:
        lines.append(f"{r['screen']:10s} {r['n']:6d} {r['win_delta_pp']:>+20.1f}"
                     f" {r['floor_delta']:>8.2f} {r['hp_delta']:>8.2f}")
    return "\n".join(lines)


def _write(path, values):
    with open(path, "w") as f:
        f.write("seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n")
        for seed, won, floor, hp in values:
            f.write(f"{seed},{won},{floor},1,{hp},80,0,0,0,1.0\n")


def selftest():
    with tempfile.TemporaryDirectory(prefix="screen_ablation_") as td:
        full = os.path.join(td, "screen_full_1k_128.csv")
        no_rest = os.path.join(td, "screen_no_rest_1k_128.csv")
        _write(full, [(1, 1, 50, 40), (2, 0, 20, 0), (3, 1, 45, 30)])
        _write(no_rest, [(1, 0, 48, 38), (2, 0, 20, 0), (3, 1, 44, 29)])
        rows = summarize(full, td, screens=("rest",))
        assert len(rows) == 1
        assert rows[0]["n"] == 3
        assert abs(rows[0]["win_delta_pp"] - 100.0 / 3.0) < 1e-9
        assert abs(rows[0]["floor_delta"] - 1.0) < 1e-9
        assert abs(rows[0]["hp_delta"] - 1.0) < 1e-9
    print("analyze_screen_ablation self-test: PASS")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", nargs="?", default="build")
    ap.add_argument("--full", default=None, help="full-arm CSV; defaults to screen_full_1k_128.csv")
    ap.add_argument("--suffix", default="1k_128.csv")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        selftest()
        return 0
    full = args.full or os.path.join(args.outdir, f"screen_full_{args.suffix}")
    rows = summarize(full, args.outdir, suffix=args.suffix)
    if args.json:
        import json
        print(json.dumps(rows, indent=2))
    else:
        print(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
