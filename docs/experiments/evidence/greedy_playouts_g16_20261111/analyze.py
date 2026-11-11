#!/usr/bin/env python3
"""Greedy playouts in G16 (PREREG.md): §775's G16 + mb4 with STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0 (GP16: greedy
playouts in boss rooms and at Shield and Spear too) against §775's G16 + mb4 in whole A20 runs with net-0420 as the
out-of-combat policy, seeds 111378256-111379279. Copied from gumbel_distill_t2_20261111/analyze.py; the arm, its env
key, the gate (nonregression with a 3 pp margin, as gumbel_learned_stop_gate_20261110) and the cost focus changed.

    python3 analyze.py NEW_ROOT REF_ROOT result.json [CLAIMS_LIST]
    python3 analyze.py --self-test

NEW_ROOT holds this campaign's unit directories (<seed>_<SET>/ with ARM-SEED.{done,log,err,env} from run_unit.sh;
verify_campaign.py --extract DIR writes DIR/out/units/<unit>/), REF_ROOT §775's (gumbel_wholerun_20261108, arms D,
G16, G32, G64).
1. Sentinel (ADR-0064): this campaign's G16 games on seeds 111378256-111378287 against §775's G16 games. A game's
   fingerprint is its rc, abort flag, whole .log except the timing fields of the BEST line (cpu_sec/run, wall), and
   the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots=`. 32 of 32 identical = REUSE_VALID;
   anything else = REUSE_INVALID, and the primary gets no verdict (CONTROL_INVALID).
2. Primary, d = Heart kill GP16 - G16 per seed, G16 = §775's game. A seed counts if both games finished rc 0 with
   all log checks and an env matching the arm (a combat abort is a counted loss); dropped seeds are listed, never
   imputed; more than 20 dropped = INCOMPLETE. Only seeds whose GP16 unit was claimed count (a unit directory in
   NEW_ROOT or a claim in CLAIMS_LIST). Gate: tools/sprt_gate.py nonregression (H0 -1.5 pp, H1 0), alpha 0.05,
   beta 0.05, look 64, cap = the analysed seeds (at most 1,024), seeds gap-free in ascending order. NOT_WORSE =
   NOT_WORSE; WORSE = WORSE; at CAP the one-sided 95% seed bootstrap bounds of the mean d (10,000 resamples, seed
   20261111) decide: NOT_WORSE_3PP if the lower bound > -3 pp, WORSE if the upper bound < 0, else INCONCLUSIVE.
   The 95% CI is reported in every case.
3. Cost (co-primary, descriptive with CIs): CPU sec per run and Gumbel simulations per run (exit line `[silver]
   whole-run Gumbel roots= sims=`), GP16 / G16 on the analysed seeds; the CPU ratio is also corrected for machine
   speed by the sentinel (this campaign's G16 CPU / §775's on the sentinel seeds). CPU quantiles (median, p90, p99,
   max) per arm.
4. Secondary (not gates): the primary's sprt_gate gainer (+2 pp); GP16 - D (§775) with 95% CI; per arm Heart kill,
   act-4 reach (final floor >= 52), mean floor, CPU sec per run, games over 1 h.
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
NEW_ARMS = ("G16", "GP16")
REF_ARMS = ("D", "G16", "G32", "G64")
ALPHA = 0.05
MARGIN = 0.03
MAX_DROPPED = 20
KEYS = ("STS_SILVER_GUMBEL_ROOT", "STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", "STS_SILVER_LEARNED_STOP",
        "STS_SILVER_GUMBEL_LEARNED_STOP", "STS_SILVER_GUMBEL_ROOT_UCB", "STS_SILVER_ROOT_PRIOR_WEIGHT",
        "STS_SILVER_TREE_PRIOR_MIN_VISITS", "STS_SILVER_NODE_REUSE_CAP", "STS_SILVER_GUMBEL_STOP_TRACE",
        "STS_SILVER_GUMBEL_ROOT_ROOMS", "STS_SILVER_GUMBEL_ROOT_SIMS", "STS_SILVER_COMBATNET_PRIOR",
        "STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS", "STS_SILVER_COMBATNET_TREE_MIN_VISITS",
        "STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE", "STS_SILVER_PRIOR_PLAYOUT_ELITE")
_G = ("16", "4", "1")
_T = ("400", "8", None, None, None, None, None, None, None, None, "0")
_GP = ("400", "8", None, None, None, None, None, None, None, "0", "0")
ENV = {"new": {"G16": _G + (None, None) + _T, "GP16": _G + (None, None) + _GP},
       "ref": {"D": (None, None, "1", None, None) + _T, "G16": _G + (None, None) + _T,
               "G32": _G + (None, None) + _T, "G64": _G + (None, None) + _T}}
SIMS = {"G16": 16000, "GP16": 16000, "D": 10000, "G32": 32000, "G64": 64000}
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
    lo1, hi1 = boot(d, 90.0)   # one-sided 95% bounds
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
        a, b = new_prints.get(("G16", s)), ref_prints.get(("G16", s))
        rows.append({"seed": s, "present": a is not None and b is not None, "identical": a is not None and a == b})
    same = sum(r["identical"] for r in rows)
    res = {"identical": same, "of": len(rows), "differing": [r["seed"] for r in rows if not r["identical"]],
           "verdict": "REUSE_VALID" if same == len(rows) else "REUSE_INVALID"}
    both = [s for s in SENTINEL if ("G16", s) in new and ("G16", s) in ref]
    if both:
        res["cpu_speed_new_over_ref"] = float(np.mean([new[("G16", s)][3] for s in both])
                                              / np.mean([ref[("G16", s)][3] for s in both]))
    return res


def main(new_root, ref_root, out, claims=None):
    new, bad_n, ab_n, mm_n, pr_n, attempted = load(new_root, "new", claims)
    ref, bad_r, ab_r, mm_r, pr_r, _ = load(ref_root, "ref")
    outdir = os.path.dirname(out) or "."
    sent = sentinel(new, ref, pr_n, pr_r)
    res = {"bad": bad_n + bad_r, "aborts": ab_n + ab_r, "env_mismatch": mm_n + mm_r, "sentinel": sent}
    p = contrast(new, ref, attempted, ("ref", "G16"), ("new", "GP16"), outdir, "GP16", gated=True)
    if sent["verdict"] != "REUSE_VALID":
        p["verdict"] = "CONTROL_INVALID"
    if "cpu_speed_new_over_ref" in sent and "cpu_ratio" in p:
        p["cpu_ratio_machine_corrected"] = p["cpu_ratio"] / sent["cpu_speed_new_over_ref"]
    res["primary"] = p
    res["secondary"] = {"GP16_minus_D": contrast(new, ref, attempted, ("ref", "D"), ("new", "GP16"), outdir,
                                                     "D", False)}
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
    for name, r in [("GP16 - G16", p), ("GP16 - D", res["secondary"]["GP16_minus_D"])]:
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
    rate = {"D": 0.30, "G16": 0.40, "G32": 0.40, "G64": 0.40, "GP16": 0.40}

    def write(root, side, unit, arm, s, k, rc=0, ab=0, env_arm=None, sims=1000, extra=""):
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
            f"[silver] whole-run Gumbel roots=10 sims={sims} (all)\n" + extra)

    outcome = {}
    for s in SEEDS:
        for arm in REF_ARMS:
            outcome[(arm, s)] = int(rng.random() < rate[arm])
            write(refr, "ref", f"{s}_{'G64' if arm == 'G64' else 'low'}", arm, s, outcome[(arm, s)])
        k = outcome[("G16", s)] if rng.random() < 0.8 else int(rng.random() < rate["GP16"])
        write(newr, "new", f"{s}_GP16", "GP16", s, k, rc=1 if s == 111378500 else 0,
              env_arm="G16" if s == 111378600 else None, ab=int(s == 111378700), sims=800)
    for s in SENTINEL:
        write(newr, "new", f"{s}_G16", "G16", s, outcome[("G16", s)])
    r = main(newr, refr, os.path.join(t, "r.json"))
    assert r["sentinel"]["verdict"] == "REUSE_VALID", r["sentinel"]
    p = r["primary"]
    assert p["dropped"] == [111378500, 111378600], p["dropped"]
    assert r["env_mismatch"] == ["new:GP16-111378600"], r["env_mismatch"]
    assert r["aborts"] == ["new:GP16-111378700"], r["aborts"]
    assert p["verdict"] in ("NOT_WORSE", "NOT_WORSE_3PP"), p["verdict"]
    assert abs(p["sims_ratio"] - 0.8) < 1e-9 and abs(p["cpu_ratio"] - 0.8) < 1e-9, p
    # a differing sentinel game (another decision count) -> CONTROL_INVALID
    s0 = SENTINEL[3]
    e = Path(newr, f"{s0}_G16", f"G16-{s0}.err")
    e.write_text(e.read_text().replace("decisions=", "decisions=9"))
    r = main(newr, refr, os.path.join(t, "r2.json"))
    assert r["sentinel"]["differing"] == [s0] and r["primary"]["verdict"] == "CONTROL_INVALID", r["sentinel"]
    e.write_text(e.read_text().replace("decisions=9", "decisions="))
    # a much worse arm -> NOT_SHOWN; a claim-only unit (lost container) is a drop
    for s in SEEDS:
        shutil.rmtree(os.path.join(newr, f"{s}_GP16"))
        write(newr, "new", f"{s}_GP16", "GP16", s, int(rng.random() < 0.25), sims=800)
    shutil.rmtree(os.path.join(newr, "111379000_GP16"))
    cl = os.path.join(t, "claims.txt")
    Path(cl).write_text("claims/111379000_GP16.a1\nclaims/111379000_GP16.a1/hb\nnot-a-claim\n")
    r = main(newr, refr, os.path.join(t, "r3.json"), cl)
    assert r["primary"]["dropped"] == [111379000] and r["primary"]["verdict"] == "WORSE", r["primary"]["verdict"]
    for s in range(111379100, 111379121):
        Path(newr, f"{s}_GP16", f"GP16-{s}.done").write_text(f"tag=GP16-{s} rc=1 start=x wall=1 abort=0")
    r = main(newr, refr, os.path.join(t, "r4.json"))
    assert r["primary"]["verdict"] == "INCOMPLETE", r["primary"]["verdict"]
    empty = os.path.join(t, "empty")
    os.makedirs(empty)
    r = main(empty, refr, os.path.join(t, "r5.json"))
    assert r["primary"]["verdict"] == "CONTROL_INVALID" and r["primary"]["n"] == 0
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:5])
