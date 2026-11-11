#!/usr/bin/env python3
"""Narrow Gumbel root (PREREG.md): GP16 (greedy_playouts_g16_20261111) with a k 4 Gumbel root without noise at 8,000
simulations, candidates from the g7f_E prior (P4) or from T1's distilled net (N4), against that campaign's GP16 games
on §775's seeds 111378256-111379279. Copied from greedy_playouts_g16_20261111/analyze.py; the arms, env keys, the
control (GP16 instead of §775's G16) and the per-arm alpha (0.025, two arms) changed.

    python3 analyze.py NEW_ROOT REF_ROOT result.json [CLAIMS_LIST]
    python3 analyze.py --self-test

NEW_ROOT holds this campaign's unit directories (<seed>_<SET>/ with ARM-SEED.{done,log,err,env} from run_unit.sh),
REF_ROOT the greedy-playout campaign's (arms G16 sentinel, GP16).
1. Sentinel (ADR-0064): this campaign's GP16 games on seeds 111378256-111378287 against that campaign's GP16 games
   (fingerprint as there). 32 of 32 identical = REUSE_VALID; else REUSE_INVALID and no verdict (CONTROL_INVALID).
2. Primary, per arm A in (P4, N4): d = Heart kill A - GP16 per seed. Counting, drops (> 20 = INCOMPLETE) and the
   claimed-unit universe as there. Gate: tools/sprt_gate.py nonregression (H0 -1.5 pp, H1 0), alpha 0.025 per arm,
   beta 0.05, look 64, cap = analysed seeds. NOT_WORSE / WORSE; at CAP the one-sided 97.5% seed bootstrap bounds
   decide: NOT_WORSE_3PP if the lower bound > -3 pp, WORSE if the upper bound < 0, else INCONCLUSIVE.
3. Cost (co-primary): CPU sec per run A / GP16 (machine-corrected by the sentinel), quantiles, Gumbel sims per run.
4. Secondary (not gates): N4 - P4 (does the net's top 4 beat the prior's?), each arm's gainer SPRT; per arm summary.
"""
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SEEDS = range(111378256, 111379280)
SENTINEL = range(111378256, 111378288)
NEW_ARMS = ("GP16", "P4", "N4")
REF_ARMS = ("G16", "GP16")
ALPHA = 0.025
MARGIN = 0.03
MAX_DROPPED = 20
KEYS = ("STS_SILVER_GUMBEL_ROOT", "STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", "STS_SILVER_LEARNED_STOP",
        "STS_SILVER_GUMBEL_LEARNED_STOP", "STS_SILVER_GUMBEL_ROOT_UCB", "STS_SILVER_ROOT_PRIOR_WEIGHT",
        "STS_SILVER_TREE_PRIOR_MIN_VISITS", "STS_SILVER_NODE_REUSE_CAP", "STS_SILVER_GUMBEL_STOP_TRACE",
        "STS_SILVER_GUMBEL_ROOT_ROOMS", "STS_SILVER_GUMBEL_ROOT_SIMS", "STS_SILVER_COMBATNET_PRIOR",
        "STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS", "STS_SILVER_COMBATNET_TREE_MIN_VISITS",
        "STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE", "STS_SILVER_PRIOR_PLAYOUT_ELITE", "STS_SILVER_GUMBEL_ROOT_NOISE")
_G = ("16", "4", "1")
_K4 = ("4", "4", "1")
_T = ("400", "8", None, None, None, None, None, None, None, None, "0", None)
_GP = ("400", "8", None, None, None, None, None, None, None, "0", "0", None)
_P4 = ("400", "8", None, None, None, None, None, None, None, "0", "0", "0")
_N4 = ("400", "8", None, None, None, None, "1", None, None, "0", "0", "0")
ENV = {"new": {"GP16": _G + (None, None) + _GP, "P4": _K4 + (None, None) + _P4, "N4": _K4 + (None, None) + _N4},
       "ref": {"G16": _G + (None, None) + _T, "GP16": _G + (None, None) + _GP}}
SIMS = {"G16": 16000, "GP16": 16000, "P4": 8000, "N4": 8000}
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)
SIMS_LINE = re.compile(r"seeds (\d+)\.\.\d+\s+asc 20\s+sims (\d+) ")
ROOTS = re.compile(r"^\[silver\] whole-run Gumbel roots=(\d+) sims=(\d+) ", re.M)
FWD = re.compile(r"^\[silver\] combat net T2 forwards: root=(\d+) tree=(\d+)$", re.M)


def env_of(path):
    if not path.exists():
        return None
    env = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return tuple(env.get(k) for k in KEYS)


def fingerprint(done, d):
    log = done.with_suffix(".log").read_text() if done.with_suffix(".log").exists() else ""
    err = done.with_suffix(".err").read_text() if done.with_suffix(".err").exists() else ""
    log = re.sub(r"cpu_sec/run=\s*[\d.]+\s+wall=\s*[\d.]+s", "", log)
    keep = [ln for ln in err.splitlines() if ln.startswith("[heart1_ppo] seed=")
            or ln.startswith("[silver] whole-run Gumbel roots=")]
    return (d["rc"], d.get("abort"), log, tuple(keep))


def load(root, side, claims=None):
    """games[(arm, seed)] = (heart, act4, floor, cpu_sec, wall, roots, sims, root_fwd, tree_fwd)."""
    games, bad, aborts, mismatch, prints, attempted = {}, [], [], [], {}, set()
    root = Path(root)
    if root.is_dir():
        attempted.update(p.name for p in root.iterdir() if p.is_dir())
    if claims:
        for line in Path(claims).read_text().split():
            m = re.match(r"^(\d+_[A-Z0-9]+)\.a\d+$", line.strip().rstrip("/").split("/")[-1])
            if m:
                attempted.add(m.group(1))
    arms = NEW_ARMS if side == "new" else REF_ARMS
    for done in sorted(root.glob("*/*.done")) if root.is_dir() else []:
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if arm not in arms:
            raise ValueError(f"unknown arm in {d['tag']}")
        key = (arm, int(seed))
        if key in games or key in prints:
            raise ValueError(f"{d['tag']} twice")
        prints[key] = fingerprint(done, d)
        log = done.with_suffix(".log").read_text() if done.with_suffix(".log").exists() else ""
        err = done.with_suffix(".err").read_text() if done.with_suffix(".err").exists() else ""
        m = WIN.search(log) if d["rc"] == "0" else None
        s = SIMS_LINE.search(log)
        if not m or not s or int(s.group(2)) != SIMS[arm] or int(s.group(1)) != int(seed):
            bad.append(f"{side}:{d['tag']}")
            continue
        if env_of(done.with_suffix(".env")) != ENV[side][arm]:
            mismatch.append(f"{side}:{d['tag']}")
            bad.append(f"{side}:{d['tag']}")
            continue
        if d.get("abort") == "1":
            aborts.append(f"{side}:{d['tag']}")
        g, st = ROOTS.search(err), FWD.search(err)
        floor = float(m.group(2))
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)), int(d["wall"]),
                      int(g.group(1)) if g else np.nan, int(g.group(2)) if g else np.nan,
                      int(st.group(1)) if st else np.nan, int(st.group(2)) if st else np.nan)
    return games, bad, aborts, mismatch, prints, attempted


def boot(x, level=95.0, seed=20261111):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    t = (100.0 - level) / 2
    return float(np.percentile(bs, t)), float(np.percentile(bs, 100.0 - t))


def boot_ratio(y, x, seed=20261111):
    """95% seed bootstrap CI of mean(y) / mean(x) (paired by seed)."""
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    r = y[i].mean(1) / x[i].mean(1)
    return float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


def gate(pairs, variant, cap, alpha):
    g = subprocess.run([sys.executable, str(REPO / "tools" / "sprt_gate.py"), pairs, "--variant", variant,
                        "--look", "64", "--cap", str(cap), "--alpha", str(alpha), "--beta", "0.05"],
                       capture_output=True, text=True)
    if g.returncode != 0:
        raise RuntimeError(f"sprt_gate failed: {g.stderr.strip()}")
    return json.loads(g.stdout)


def contrast(new, ref, attempted, a, b, outdir, name, gated=True):
    src = {"new": new, "ref": ref}
    universe = [s for s in SEEDS if f"{s}_{b[1]}" in attempted]
    seeds = [s for s in universe if (a[1], s) in src[a[0]] and (b[1], s) in src[b[0]]]
    x = np.array([src[a[0]][(a[1], s)] for s in seeds], float).reshape(-1, 9)
    y = np.array([src[b[0]][(b[1], s)] for s in seeds], float).reshape(-1, 9)
    dropped = [s for s in universe if s not in set(seeds)]
    r = {"control": f"{a[0]}:{a[1]}", "arm": f"{b[0]}:{b[1]}", "n": len(seeds), "dropped": dropped}
    if not seeds:
        r["verdict"] = "INCOMPLETE" if gated else None
        return r
    d = y[:, 0] - x[:, 0]
    r.update({"heart_control": float(x[:, 0].mean()), "heart_arm": float(y[:, 0].mean()), "d": float(d.mean()),
              "ci95": boot(d), "act4_d": float((y[:, 1] - x[:, 1]).mean()), "act4_ci95": boot(y[:, 1] - x[:, 1]),
              "floor_d": float((y[:, 2] - x[:, 2]).mean()), "floor_ci95": boot(y[:, 2] - x[:, 2]),
              "cpu_ratio": float(y[:, 3].mean() / x[:, 3].mean()), "cpu_ratio_ci95": boot_ratio(y[:, 3], x[:, 3]),
              "arm_only": int((d > 0).sum()), "control_only": int((d < 0).sum())})
    ok = ~np.isnan(x[:, 6]) & ~np.isnan(y[:, 6])
    if ok.any():
        r["sims_ratio"] = float(y[ok, 6].mean() / x[ok, 6].mean())
        r["sims_ratio_ci95"] = boot_ratio(y[ok, 6], x[ok, 6])
        r["roots_ratio"] = float(y[ok, 5].mean() / x[ok, 5].mean())
    if not gated:
        return r
    lo1, hi1 = boot(d, 95.0)   # one-sided 97.5% bounds
    pairs = os.path.join(outdir, f"pairs_{name}.csv")
    with open(pairs, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key", "a", "b"])
        for k, (p, q) in enumerate(zip(x[:, 0], y[:, 0])):
            w.writerow([k, int(p), int(q)])
    cap = min(1024, len(seeds))
    r["one_sided95"] = [lo1, hi1]
    r["sprt"] = gate(pairs, "nonregression", cap, ALPHA)
    r["sprt_gainer"] = gate(pairs, "gainer", cap, ALPHA)
    sv = r["sprt"].get("verdict")
    if len(dropped) > MAX_DROPPED:
        v = "INCOMPLETE"
    elif sv in ("NOT_WORSE", "WORSE"):
        v = sv
    elif sv == "CAP":
        v = "NOT_WORSE_3PP" if lo1 > -MARGIN else ("WORSE" if hi1 < 0 else "INCONCLUSIVE")
    else:
        v = "PARTIAL"
    r["verdict"] = v
    r["gainer"] = r["sprt_gainer"].get("verdict")
    q = lambda v_: [float(np.percentile(v_, k)) for k in (50, 90, 99, 100)]
    r["cpu_quantiles_control"], r["cpu_quantiles_arm"] = q(x[:, 3]), q(y[:, 3])
    return r


def sentinel(new, ref, new_prints, ref_prints):
    rows = []
    for s in SENTINEL:
        a, b = new_prints.get(("GP16", s)), ref_prints.get(("GP16", s))
        rows.append({"seed": s, "present": a is not None and b is not None, "identical": a is not None and a == b})
    same = sum(r["identical"] for r in rows)
    res = {"identical": same, "of": len(rows), "differing": [r["seed"] for r in rows if not r["identical"]],
           "verdict": "REUSE_VALID" if same == len(rows) else "REUSE_INVALID"}
    both = [s for s in SENTINEL if ("GP16", s) in new and ("GP16", s) in ref]
    if both:
        res["cpu_speed_new_over_ref"] = float(np.mean([new[("GP16", s)][3] for s in both])
                                              / np.mean([ref[("GP16", s)][3] for s in both]))
    return res


def main(new_root, ref_root, out, claims=None):
    new, bad_n, ab_n, mm_n, pr_n, attempted = load(new_root, "new", claims)
    ref, bad_r, ab_r, mm_r, pr_r, _ = load(ref_root, "ref")
    outdir = os.path.dirname(out) or "."
    sent = sentinel(new, ref, pr_n, pr_r)
    res = {"bad": bad_n + bad_r, "aborts": ab_n + ab_r, "env_mismatch": mm_n + mm_r, "sentinel": sent}
    prim = {}
    for arm in ("P4", "N4"):
        p = contrast(new, ref, attempted, ("ref", "GP16"), ("new", arm), outdir, arm, gated=True)
        if sent["verdict"] != "REUSE_VALID":
            p["verdict"] = "CONTROL_INVALID"
        if "cpu_speed_new_over_ref" in sent and "cpu_ratio" in p:
            p["cpu_ratio_machine_corrected"] = p["cpu_ratio"] / sent["cpu_speed_new_over_ref"]
        prim[arm] = p
    res["primary"] = prim
    res["secondary"] = {"N4_minus_P4": contrast(new, new, attempted, ("new", "P4"), ("new", "N4"), outdir, "NP",
                                                 False)}
    per_arm = {}
    for side, games, arms in (("new", new, NEW_ARMS), ("ref", ref, REF_ARMS)):
        for arm in arms:
            vals = [v for (a, s), v in games.items() if a == arm and s in SEEDS]
            if not vals:
                continue
            g = np.array(vals, float)
            per_arm[f"{side}:{arm}"] = {"games": len(g), "heart": float(g[:, 0].mean()), "act4": float(g[:, 1].mean()),
                                        "floor": float(g[:, 2].mean()), "cpu_sec": float(g[:, 3].mean()),
                                        "long_games": int((g[:, 4] > 3600).sum()), "max_wall": int(g[:, 4].max())}
    res["per_arm"] = per_arm
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"bad {len(res['bad'])} (env mismatch {len(res['env_mismatch'])}) aborts {len(res['aborts'])}  sentinel "
          f"{sent['identical']}/{sent['of']} {sent['verdict']}")
    for name, r in [("P4 - GP16", prim["P4"]), ("N4 - GP16", prim["N4"]), ("N4 - P4", res["secondary"]["N4_minus_P4"])]:
        if not r["n"]:
            print(f"{name}: no analysable seed -> {r.get('verdict')}")
            continue
        print(f"{name}: n {r['n']} dropped {len(r['dropped'])}  heart {100 * r['heart_control']:.2f}% -> "
              f"{100 * r['heart_arm']:.2f}%  d {100 * r['d']:+.2f} [{100 * r['ci95'][0]:+.2f}, "
              f"{100 * r['ci95'][1]:+.2f}] pp  act4 d {100 * r['act4_d']:+.2f} pp  cpu ratio {r['cpu_ratio']:.3f}"
              + (f"  sims ratio {r['sims_ratio']:.3f}" if "sims_ratio" in r else "")
              + f"  verdict {r.get('verdict')}"
              + (f" (sprt {r['sprt'].get('verdict')}), gainer {r['gainer']}" if "sprt" in r else "")
              + (f"  cpu q50/90/99/max {[round(v) for v in r['cpu_quantiles_arm']]}" if "cpu_quantiles_arm" in r else ""))
    return res


def self_test():
    """Synthetic campaign: sentinel valid / invalid, drops, an abort, a wrong env -> verdicts."""
    import random
    import shutil
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    newr, refr = os.path.join(t, "new"), os.path.join(t, "ref")

    def write(root, side, unit, arm, s, k, rc=0, ab=0, env_arm=None, sims=1000):
        dd = os.path.join(root, unit)
        os.makedirs(dd, exist_ok=True)
        Path(dd, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=20 abort={ab}")
        Path(dd, f"{arm}-{s}.env").write_text("STS_FAIR=1\n" + "".join(
            f"{k_}={v}\n" for k_, v in zip(KEYS, ENV[side][env_arm or arm]) if v is not None))
        Path(dd, f"{arm}-{s}.log").write_text(
            f"BEST stack config: x  seeds {s}..{s}  asc 20  sims {SIMS[arm]}  threads 1\n"
            f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  avg_hp_end= 0.0   "
            f"cpu_sec/run={sims / 50:.2f}   wall={rng.uniform(10, 30):.1f}s\n")
        Path(dd, f"{arm}-{s}.err").write_text(
            f"[heart1] loaded /root/{rng.random()}/net-0420.bin (x)\n[heart1_ppo] seed={s} decisions={k + 3}\n"
            f"[silver] whole-run Gumbel roots=10 sims={sims} (all)\n")

    outcome = {}
    for s in SEEDS:
        outcome[s] = int(rng.random() < 0.4)
        write(refr, "ref", f"{s}_GP16", "GP16", s, outcome[s])
        k = outcome[s] if rng.random() < 0.85 else int(rng.random() < 0.4)
        write(newr, "new", f"{s}_P4", "P4", s, k, rc=1 if s == 111378500 else 0,
              env_arm="N4" if s == 111378600 else None, ab=int(s == 111378700), sims=500)
        write(newr, "new", f"{s}_N4", "N4", s, outcome[s] if rng.random() < 0.85 else int(rng.random() < 0.4),
              sims=500)
    for s in SENTINEL[:16]:
        write(refr, "ref", f"{s}_G16", "G16", s, outcome[s])
    for s in SENTINEL:
        write(newr, "new", f"{s}_GP16", "GP16", s, outcome[s])
    r = main(newr, refr, os.path.join(t, "r.json"))
    assert r["sentinel"]["verdict"] == "REUSE_VALID", r["sentinel"]
    p = r["primary"]["P4"]
    assert p["dropped"] == [111378500, 111378600], p["dropped"]
    assert r["env_mismatch"] == ["new:P4-111378600"], r["env_mismatch"]
    assert r["aborts"] == ["new:P4-111378700"], r["aborts"]
    assert p["verdict"] in ("NOT_WORSE", "NOT_WORSE_3PP"), p["verdict"]
    assert abs(p["cpu_ratio"] - 0.5) < 1e-9, p["cpu_ratio"]
    assert r["primary"]["N4"]["verdict"] in ("NOT_WORSE", "NOT_WORSE_3PP"), r["primary"]["N4"]["verdict"]
    s0 = SENTINEL[3]
    e = Path(newr, f"{s0}_GP16", f"GP16-{s0}.err")
    e.write_text(e.read_text().replace("decisions=", "decisions=9"))
    r = main(newr, refr, os.path.join(t, "r2.json"))
    assert r["sentinel"]["differing"] == [s0] and r["primary"]["N4"]["verdict"] == "CONTROL_INVALID", r["sentinel"]
    e.write_text(e.read_text().replace("decisions=9", "decisions="))
    for s in SEEDS:
        shutil.rmtree(os.path.join(newr, f"{s}_N4"))
        write(newr, "new", f"{s}_N4", "N4", s, int(rng.random() < 0.2), sims=500)
    r = main(newr, refr, os.path.join(t, "r3.json"))
    assert r["primary"]["N4"]["verdict"] == "WORSE", r["primary"]["N4"]["verdict"]
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:5])
