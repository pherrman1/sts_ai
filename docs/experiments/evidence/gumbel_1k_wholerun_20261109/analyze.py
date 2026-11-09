#!/usr/bin/env python3
"""Gumbel 1k in whole runs (PREREG.md): G1 (G16 + mb4 at 1,000 simulations) against combat B (B1).

usage: python3 -I analyze.py UNITS_DIR REF_UNITS_DIR OUT.json | --self-test
  UNITS_DIR: this campaign's extracted out/units (one dir per unit, ARM-SEED.{done,log,err,env} inside);
  REF_UNITS_DIR: §775's extracted out/units (D, G16 games), read with ../gumbel_tuning_20261109/wholerun/analyze.py's
  loader (its env and sims checks).

A game counts if its .done has rc 0, the log has the BEST line with seed and sims 1000, and its .env has the arm's
values (ENV). Otherwise it is a drop; a seed with a drop in either arm is left out of the pairs and counted.
Primary: Heart kill G1 - B1 over paired seeds, 95% seed bootstrap (10,000 resamples, seed 20261109): G1_BETTER if lo > 0,
G1_WORSE if hi < 0, else NO_DIFFERENCE_SHOWN; NOT_EVALUABLE if more than 10 seeds dropped.
Secondary: per arm Heart, Act-4 reach (floor >= 52), final floor, CPU per run; G1 and B1 against §775's D and G16 on
the same seeds; aborts per arm; G1's Gumbel roots and simulations.
"""
import importlib.util, json, re, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SEEDS = range(111378256, 111378768)
ARMS = ("B1", "G1")
MAX_DROPPED = 10
KEYS = ("STS_SILVER_GUMBEL_ROOT", "STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", "STS_SILVER_LEARNED_STOP", "STS_SILVER_ACT4_STRONG",
        "STS_SILVER_ROOT_PRIOR_WEIGHT", "STS_SILVER_TREE_PRIOR_MIN_VISITS", "STS_SILVER_PRIOR_PLAYOUT_ELITE",
        "STS_OOC_MCTS", "STS_SILVER_GUMBEL_ROOT_UCB", "STS_SILVER_NODE_REUSE_CAP")
_B = ("0", "0", "400", "8", "0", "0", None, None)
ENV = {"B1": (None, None) + _B, "G1": ("16", "4") + _B}
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)
SIMS_LINE = re.compile(r"seeds (\d+)\.\.\d+\s+asc 20\s+sims (\d+) ")
ROOTS = re.compile(r"^\[silver\] whole-run Gumbel roots=(\d+) sims=(\d+) ", re.M)


def env_of(path):
    if not path.exists():
        return None
    env = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return tuple(env.get(k) for k in KEYS)


def load(root):
    """games[(arm, seed)] = (heart, act4, floor, cpu_sec, abort, gumbel roots, gumbel sims); drops = [tag, ...]."""
    games, drops, seen = {}, [], set()
    for done in sorted(Path(root).glob("*/*.done")):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if arm not in ARMS:
            raise ValueError(f"unknown arm in {d['tag']}")
        if (arm, int(seed)) in seen:
            raise ValueError(f"{d['tag']} twice")
        seen.add((arm, int(seed)))
        log = done.with_suffix(".log").read_text() if done.with_suffix(".log").exists() else ""
        err = done.with_suffix(".err").read_text() if done.with_suffix(".err").exists() else ""
        m = WIN.search(log) if d["rc"] == "0" else None
        s = SIMS_LINE.search(log)
        if (not m or not s or int(s.group(2)) != 1000 or int(s.group(1)) != int(seed)
                or env_of(done.with_suffix(".env")) != ENV[arm]):
            drops.append(d["tag"])
            continue
        g = ROOTS.search(err)
        floor = float(m.group(2))
        games[(arm, int(seed))] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)),
                                   int(d.get("abort", "0")), int(g.group(1)) if g else None, int(g.group(2)) if g else None)
    return games, drops, seen


def boot(x, seed=20261109):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def contrast(a, b, seeds):
    """b - a over seeds (a, b: seed -> game tuple)."""
    s = [x for x in seeds if x in a and x in b]
    if not s:
        return dict(seeds=0)
    out = dict(seeds=len(s))
    for i, name in ((0, "heart_pp"), (1, "act4_pp"), (2, "floor")):
        x = np.array([b[k][i] - a[k][i] for k in s], float) * (100.0 if name.endswith("pp") else 1.0)
        out[name] = dict(mean=float(x.mean()), ci95=boot(x))
    out["only_b"] = int(sum(b[k][0] and not a[k][0] for k in s))
    out["only_a"] = int(sum(a[k][0] and not b[k][0] for k in s))
    out["cpu_ratio"] = float(sum(b[k][3] for k in s) / max(1e-9, sum(a[k][3] for k in s)))
    return out


def per_arm(g, seeds):
    s = [x for x in seeds if x in g]
    if not s:
        return dict(games=0)
    v = np.array([g[k][:4] for k in s], float)
    return dict(games=len(s), heart=float(v[:, 0].mean()), act4=float(v[:, 1].mean()), floor=float(v[:, 2].mean()),
                cpu_per_run=float(v[:, 3].mean()), cpu_per_floor=float(v[:, 3].sum() / v[:, 2].sum()),
                aborts=int(sum(g[k][4] for k in s)))


def analyze(games, drops, seen, ref=None):
    arm = {a: {s: v for (b, s), v in games.items() if b == a} for a in ARMS}
    dropped = sorted({int(t.rsplit("-", 1)[1]) for t in drops}
                     | {s for s in SEEDS if any((a, s) not in seen for a in ARMS)})
    paired = [s for s in SEEDS if s in arm["B1"] and s in arm["G1"]]
    prim = contrast(arm["B1"], arm["G1"], paired)
    lo, hi = prim["heart_pp"]["ci95"] if paired else (0, 0)
    verdict = ("NOT_EVALUABLE" if len(dropped) > MAX_DROPPED or not paired else "G1_BETTER" if lo > 0
               else "G1_WORSE" if hi < 0 else "NO_DIFFERENCE_SHOWN")
    g1 = [arm["G1"][s] for s in paired if arm["G1"][s][5]]
    res = dict(paired_seeds=len(paired), dropped_seeds=dropped, drops=sorted(drops),
               primary=dict(contrast="G1 - B1", **prim, verdict=verdict),
               per_arm={a: per_arm(arm[a], paired) for a in ARMS},
               g1_gumbel=dict(roots_per_run=float(np.mean([x[5] for x in g1])) if g1 else None,
                              sims_per_run=float(np.mean([x[6] for x in g1])) if g1 else None))
    if ref is not None:
        r = {a: {s: (v[0], v[1], v[2], v[3]) for (b, s), v in ref.items() if b == a} for a in ("D", "G16")}
        res["per_arm"].update({f"ref:{a}": per_arm({s: v + (0,) for s, v in r[a].items()}, paired) for a in r})
        res["vs_ref"] = {f"{x} - {a}": contrast(r[a], arm[x], paired) for a in r for x in ARMS}
    return res


def main(units, ref_units, out):
    games, drops, seen = load(units)
    spec = importlib.util.spec_from_file_location("wr", HERE.parent / "gumbel_tuning_20261109" / "wholerun" / "analyze.py")
    W = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(W)
    ref, ref_bad = W.load(ref_units, "ref")[:2]
    res = analyze(games, drops, seen, ref)
    res["ref_bad"] = [b for b in ref_bad if int(b.rsplit("-", 1)[1]) in SEEDS]
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    p = res["primary"]
    print(f"paired {res['paired_seeds']}, dropped {len(res['dropped_seeds'])}; G1 - B1 Heart {p['heart_pp']['mean']:+.2f} pp "
          f"[{p['heart_pp']['ci95'][0]:+.2f}, {p['heart_pp']['ci95'][1]:+.2f}] -> {p['verdict']}")
    for a, v in res["per_arm"].items():
        print(f"  {a}: Heart {100 * v['heart']:.2f}%  Act4 {100 * v['act4']:.2f}%  floor {v['floor']:.2f}  "
              f"cpu/run {v['cpu_per_run']:.1f} s  aborts {v['aborts']}")
    for k, v in res.get("vs_ref", {}).items():
        print(f"  {k}: {v['heart_pp']['mean']:+.2f} pp [{v['heart_pp']['ci95'][0]:+.2f}, {v['heart_pp']['ci95'][1]:+.2f}] "
              f"cpu x{v['cpu_ratio']:.2f}")


def self_test():
    rng = np.random.default_rng(1)
    games, seen = {}, set()
    for s in SEEDS:
        for a, p in (("B1", 0.2), ("G1", 0.4)):
            w = int(rng.random() < p)
            games[(a, s)] = (w, w, 56.0 if w else 30.0, 20.0 if a == "B1" else 25.0, 0, 300 if a == "G1" else None,
                             280000 if a == "G1" else None)
            seen.add((a, s))
    r = analyze(games, [], seen)
    assert r["paired_seeds"] == 512 and r["primary"]["verdict"] == "G1_BETTER", r["primary"]
    assert abs(r["primary"]["cpu_ratio"] - 1.25) < 1e-9
    del games[("G1", 111378300)]
    r = analyze(games, ["B1-111378301"], seen - {("G1", 111378300)})
    assert r["dropped_seeds"] == [111378300, 111378301] and r["paired_seeds"] == 511, r["dropped_seeds"]
    r = analyze(games, [f"B1-{s}" for s in range(111378400, 111378411)], seen)
    assert r["primary"]["verdict"] == "NOT_EVALUABLE"
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 4:
        main(*sys.argv[1:])
    else:
        sys.exit(__doc__)
