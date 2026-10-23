#!/usr/bin/env python3
"""On-policy leaf round 1, README analysis step 6: two leaf nets in the same smoke, paired per fight.

DIR_A and DIR_B are the output dirs of two run_smoke16.sh runs (one net each, same sources). Both are read with the
loader and score of ../silver_leaf_label_data_20261023/smoke/analyze2.py (fight score 0 on death, else 53 + HP +
11 x potions + 0.25 x gold + 2 x max HP; arm value per fight = mean of the R = 2 redraws). The production arm
base10000 must be identical in both runs, fight by fight and redraw by redraw (the harness is seed-deterministic);
otherwise the script stops. A fight counts when every arm row of both runs is valid and every arm has both redraws.
Contrasts per fight, B - A (the two nets) and each net - base10000, for score, win, HP lost and decisions; all fights,
by room class and by act; 95% CI = analyze2.py's bootstrap over source seeds (10,000 resamples, RNG seed 0).

usage: pair.py OUT.json DIR_A DIR_B
"""
import importlib.util
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "analyze2", os.path.join(HERE, "..", "silver_leaf_label_data_20261023", "smoke", "analyze2.py"))
an = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(an)
METRICS = ("score", "win", "hpLoss", "decisions")


def fights(d):
    """stateId -> (state row, {arm: metrics}, {arm: redraw outcomes}) for the valid complete fights of DIR."""
    states, valid, _cpu, _dec, samples, _shards, work, _reasons = an.load([d])
    out, dropped = {}, 0
    for sid, st in states.items():
        per, raw = {}, {}
        for a in ("base10000", "head10000"):
            rows = sorted(samples.get((sid, a), []), key=lambda r: int(r["k"]))
            if not valid[sid] or len(rows) != an.R:
                break
            dead = [r["outcome"] == "DEATH" for r in rows]
            pre = float(st["preHp"])
            per[a] = {"score": sum(map(an.score, rows)) / an.R, "win": 1.0 - sum(dead) / an.R,
                      "hpLoss": sum(pre - (0.0 if x else float(r["curHp"])) for r, x in zip(rows, dead)) / an.R,
                      "decisions": work[(sid, a)][4] / an.R}
            raw[a] = [{k: r[k] for k in ("k", "outcome", "curHp", "maxHp", "gold", "potionCount")} for r in rows]
        else:
            out[sid] = (st, per, raw)
            continue
        dropped += 1
    return out, dropped


def main():
    out_path, dir_a, dir_b = sys.argv[1:4]
    fa, drop_a = fights(dir_a)
    fb, drop_b = fights(dir_b)
    shared = sorted(set(fa) & set(fb))
    diff = [s for s in shared if fa[s][2]["base10000"] != fb[s][2]["base10000"]]
    if diff:
        raise SystemExit(f"base10000 differs between the runs in {len(diff)} fights, e.g. {diff[:3]}")
    arms = {"base": lambda s: fa[s][1]["base10000"], "A": lambda s: fa[s][1]["head10000"],
            "B": lambda s: fb[s][1]["head10000"]}
    subsets = [("all", lambda st: True)]
    subsets += [(rc.lower(), lambda st, rc=rc: st["roomClass"] == rc) for rc in ("NORMAL", "ELITE", "BOSS", "OTHER")]
    subsets += [(f"act{a}", lambda st, a=a: st["act"] == str(a)) for a in (1, 2, 3, 4)]
    result = {"dirA": dir_a, "dirB": dir_b, "fights": len(shared), "onlyA": len(set(fa) - set(fb)),
              "onlyB": len(set(fb) - set(fa)), "droppedA": drop_a, "droppedB": drop_b,
              "sources": len({fa[s][0]["sourceSeed"] for s in shared}), "baseIdentical": True,
              "arms": {k: {m: sum(f(s)[m] for s in shared) / len(shared) for m in METRICS} for k, f in arms.items()},
              "contrasts": {}}
    for x, y in (("B", "A"), ("A", "base"), ("B", "base")):
        for name, keep in subsets:
            ids = [s for s in shared if keep(fa[s][0])]
            if not ids:
                continue
            for m in METRICS:
                per_seed = defaultdict(list)
                for s in ids:
                    per_seed[fa[s][0]["sourceSeed"]].append(arms[x](s)[m] - arms[y](s)[m])
                mean, lo, hi = an.boot(per_seed)
                result["contrasts"][f"{x}-{y}/{name}/{m}"] = {"mean": mean, "ci95": [lo, hi], "n": len(ids)}
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"{result['fights']} fights from {result['sources']} sources (only A {result['onlyA']}, only B "
          f"{result['onlyB']}; dropped A {drop_a}, B {drop_b}); base10000 identical in both runs")
    for k, c in result["contrasts"].items():
        if k.endswith("/score") or k.endswith("/hpLoss") or "/all/" in k:
            print(f"{k}: {c['mean']:+.3f} [{c['ci95'][0]:+.3f}, {c['ci95'][1]:+.3f}] n={c['n']}")


if __name__ == "__main__":
    main()
