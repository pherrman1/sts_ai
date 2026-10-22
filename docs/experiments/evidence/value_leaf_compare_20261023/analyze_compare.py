#!/usr/bin/env python3
"""Value-head plan stages 1-2: referee level and leaf-compare predictions from STS_OOC_MCTS_LEAF_COMPARE runs.

usage: python3 -I analyze_compare.py DIR [--json OUT] [--boot 2000] [--rng 20261023]

DIR is the --extract dir of `verify_campaign.py` (its out/units/<seed>/ directories) or a directory of seed
directories. Each seed directory holds LC-<seed>.done (rc), LC-<seed>.jsonl[.gz] (heartoutcomegen records; the last
line is the outcome footer) and LC-<seed>.compare.jsonl[.gz] (one row per searched root). A game is valid when its rc
is 0 and its footer says complete and integrityPassed; invalid games are listed and left out, not replaced.

Definitions (PREREG.md):
- Referee value of an action at a root: the mean over its n rollouts of `value` (R_full: played to the end of the
  game) or `actEnd` (R_act: to the end of the root's act, then the calibrated X2-B). Rollout i of every action at a
  root shares one random stream, so differences are paired by i.
- Flip: an arm's search picked an action other than the played one (arm not aborted, a pick present).
- Per game and arm: D = the sum over its flipped roots of mean_i [ref(arm pick, i) - ref(played, i)].
- Predicted delta Heart rate of an arm = mean of D over games (games with no flip count as 0); 95% interval from a
  seed bootstrap.
- Level by act: mean over roots in the act of the played action's referee value, against the mean over the same
  roots of the game's real outcome (1 = Heart killed).
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REFEREES = ("value", "actEnd")   # R_full, R_act


def read_lines(base: Path):
    """Lines of base (.jsonl) or base.gz; None if neither exists."""
    if base.exists():
        return base.read_text().splitlines()
    gz = base.with_name(base.name + ".gz")
    if gz.exists():
        return gzip.decompress(gz.read_bytes()).decode().splitlines()
    return None


def load_game(seed_dir: Path):
    seed = seed_dir.name
    done = seed_dir / f"LC-{seed}.done"
    rc = re.search(r"rc=(-?\d+)", done.read_text()) if done.exists() else None
    if not rc or rc.group(1) != "0":
        return None, f"rc {rc.group(1) if rc else 'missing'}"
    rec = read_lines(seed_dir / f"LC-{seed}.jsonl")
    cmp_ = read_lines(seed_dir / f"LC-{seed}.compare.jsonl")
    if rec is None or cmp_ is None:
        return None, "missing files"
    footer = json.loads(rec[-1]) if rec else {}
    if footer.get("type") != "outcome" or not footer.get("complete") or not footer.get("integrityPassed"):
        return None, "no complete footer"
    rows = [json.loads(line) for line in cmp_ if line.strip()]
    return {"seed": int(seed), "y": 1 if footer.get("heartKilled") else 0, "rows": rows,
            "finalAct": footer.get("finalAct")}, None


def paired_mean(ref: dict, a: str, b: str, key: str):
    """mean_i [ref[a][i] - ref[b][i]] over i where both rollouts are usable; None if none is."""
    la, lb = ref.get(a, []), ref.get(b, [])
    diffs = []
    for ea, eb in zip(la, lb):
        if "error" in ea or "error" in eb or key not in ea or key not in eb:
            continue
        if key == "value" and not (ea.get("terminal") and eb.get("terminal")):
            continue
        diffs.append(ea[key] - eb[key])
    if not diffs:
        return None, None
    m = sum(diffs) / len(diffs)
    var = statistics.pvariance(diffs) if len(diffs) > 1 else 0.0
    return m, var


def action_mean(ref: dict, a: str, key: str):
    vals = [e[key] for e in ref.get(a, []) if "error" not in e and key in e
            and (key != "value" or e.get("terminal"))]
    return (sum(vals) / len(vals)) if vals else None


def per_game(game: dict, arms: list[str]):
    out = {"D": {k: {a: 0.0 for a in arms} for k in REFEREES},
           "flips": defaultdict(int), "flipsByAct": defaultdict(lambda: defaultdict(int)),
           "roots": 0, "rootsByAct": defaultdict(int), "pairVar": {k: defaultdict(list) for k in REFEREES},
           "advantages": {k: defaultdict(list) for k in REFEREES},
           "level": {k: defaultdict(list) for k in REFEREES}, "missing": defaultdict(int),
           "armCpu": defaultdict(float), "refCpu": 0.0, "rollouts": 0, "nonTerminal": 0, "errors": 0}
    for row in game["rows"]:
        act = row.get("act")
        main = row["main"].get("selectedId")
        ref = (row.get("referee") or {}).get("actions", {})
        out["refCpu"] += (row.get("referee") or {}).get("cpuSeconds", 0.0)
        for lst in ref.values():
            for e in lst:
                out["rollouts"] += 1
                if "error" in e:
                    out["errors"] += 1
                elif not e.get("terminal"):
                    out["nonTerminal"] += 1
        out["roots"] += 1
        out["rootsByAct"][act] += 1
        played = str(main)
        for k in REFEREES:
            lv = action_mean(ref, played, k)
            if lv is not None:
                out["level"][k][act].append(lv)
        for a in arms:
            arm = row["arms"].get(a)
            if arm is None:
                out["missing"][a] += 1
                continue
            out["armCpu"][a] += arm.get("cpuSeconds", 0.0)
            if "error" in arm:
                out["missing"][a + ":error"] += 1
                continue
            pick = arm.get("selectedId")
            if arm.get("aborted") or pick is None or pick == main:
                continue
            out["flips"][a] += 1
            out["flipsByAct"][a][act] += 1
            for k in REFEREES:
                m, var = paired_mean(ref, str(pick), played, k)
                if m is None:
                    out["missing"][a + ":" + k] += 1
                    continue
                out["D"][k][a] += m
                out["advantages"][k][a].append(m)
                out["pairVar"][k][a].append(var)
    return out


def boot_ci(values: list[float], boots: int, rng: random.Random):
    n = len(values)
    if n == 0:
        return None
    means = []
    for _ in range(boots):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return [means[int(0.025 * boots)], means[int(0.975 * boots) - 1]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("units")
    ap.add_argument("--json")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--rng", type=int, default=20261023)
    args = ap.parse_args()
    games, excluded = [], {}
    units = Path(args.units)
    if (units / "out" / "units").is_dir():
        units = units / "out" / "units"
    for d in sorted(p for p in units.iterdir() if p.is_dir()):
        g, why = load_game(d)
        if g is None:
            excluded[d.name] = why
        else:
            games.append(g)
    if not games:
        print("no games", file=sys.stderr)
        return 2
    arms = sorted({a for g in games for r in g["rows"] for a in r.get("arms", {})})
    per = [per_game(g, arms) for g in games]
    rng = random.Random(args.rng)
    report = {"games": len(games), "excluded": excluded, "arms": arms,
              "heartRate": sum(g["y"] for g in games) / len(games), "referees": {}}
    roots = sum(p["roots"] for p in per)
    report["roots"] = roots
    report["rootsByAct"] = {str(a): sum(p["rootsByAct"].get(a, 0) for p in per) for a in (1, 2, 3, 4)}
    report["rollouts"] = sum(p["rollouts"] for p in per)
    report["rolloutErrors"] = sum(p["errors"] for p in per)
    report["rolloutsNonTerminal"] = sum(p["nonTerminal"] for p in per)
    report["refereeCpuSeconds"] = sum(p["refCpu"] for p in per)
    report["armCpuSeconds"] = {a: sum(p["armCpu"][a] for p in per) for a in arms}
    report["flips"] = {a: sum(p["flips"][a] for p in per) for a in arms}
    report["flipRate"] = {a: report["flips"][a] / roots for a in arms}
    report["flipsByAct"] = {a: {str(act): sum(p["flipsByAct"][a].get(act, 0) for p in per) for act in (1, 2, 3, 4)}
                            for a in arms}
    report["missing"] = {k: sum(p["missing"].get(k, 0) for p in per) for k in
                         sorted({k for p in per for k in p["missing"]})}
    for k in REFEREES:
        rk = {"predicted": {}, "level": {}}
        for a in arms:
            ds = [p["D"][k][a] for p in per]
            adv = [x for p in per for x in p["advantages"][k][a]]
            pv = [x for p in per for x in p["pairVar"][k][a]]
            ci = boot_ci(ds, args.boot, rng)
            rk["predicted"][a] = {
                "deltaHeart": sum(ds) / len(ds), "ci95": ci,
                "flipsUsed": len(adv), "meanAdvantage": (sum(adv) / len(adv)) if adv else None,
                "seMeanAdvantage": (statistics.stdev(adv) / math.sqrt(len(adv))) if len(adv) > 1 else None,
                "meanPairVariance": (sum(pv) / len(pv)) if pv else None}
            # split halves by seed parity
            for half in (0, 1):
                hs = [p["D"][k][a] for p, g in zip(per, games) if g["seed"] % 2 == half]
                rk["predicted"][a][f"half{half}"] = (sum(hs) / len(hs)) if hs else None
        for act in (1, 2, 3, 4):
            ref_vals, real_vals, per_game_diff = [], [], []
            for p, g in zip(per, games):
                lv = p["level"][k].get(act, [])
                ref_vals += lv
                real_vals += [g["y"]] * len(lv)
                if lv:
                    per_game_diff.append((sum(lv), g["y"] * len(lv), len(lv)))
            if not ref_vals:
                continue
            ref_mean, real_mean = sum(ref_vals) / len(ref_vals), sum(real_vals) / len(real_vals)
            # bootstrap the ratio-of-sums difference over games
            boots = []
            n = len(per_game_diff)
            for _ in range(args.boot):
                sr = sy = sn = 0.0
                for _ in range(n):
                    a_, b_, c_ = per_game_diff[rng.randrange(n)]
                    sr += a_; sy += b_; sn += c_
                boots.append((sr - sy) / sn)
            boots.sort()
            rk["level"][str(act)] = {"roots": len(ref_vals), "referee": ref_mean, "real": real_mean,
                                     "diff": ref_mean - real_mean,
                                     "ci95": [boots[int(0.025 * args.boot)], boots[int(0.975 * args.boot) - 1]],
                                     "pass": abs(ref_mean - real_mean) <= 0.05}
        rk["levelPass"] = bool(rk["level"]) and all(v["pass"] for v in rk["level"].values()) and len(rk["level"]) == 4
        report["referees"]["R_full" if k == "value" else "R_act"] = rk
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.json:
        Path(args.json).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
