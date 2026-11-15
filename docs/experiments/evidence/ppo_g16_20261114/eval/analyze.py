#!/usr/bin/env python3
"""PG16H24 evaluation (../PREREG.md, section Evaluation; EVAL.md): the PPO run's final net net-0046 (P46) against its
start net net-0420 as the whole out-of-combat policy (temperature 0, no OOC MCTS), both on §775's G16 + mb4 combat
stack (Heart 40k), seeds 111378256-111379279. Copied from gumbel_g12_heart24_20261113/analyze.py; the arm (net-0046
instead of 12k/Heart 24k), the gate (gainer instead of nonregression), the bootstrap seed and the docstring changed.

    python3 analyze.py NEW_ROOT REF_ROOT result.json [CLAIMS_LIST]
    python3 analyze.py --self-test

NEW_ROOT holds this campaign's unit directories (<seed>_<SET>/ with ARM-SEED.{done,log,err,env} from run_unit.sh;
verify_campaign.py --extract DIR writes DIR/out/units/<unit>/), REF_ROOT §775's (gumbel_wholerun_20261108, arms D,
G16, G32, G64). §775's G16 games are net-0420's games on this stack.
1. Sentinel (ADR-0064): this campaign's G16 games (net-0420) on seeds 111378256-111378287 against §775's G16 games.
   A game's fingerprint is its rc, abort flag, whole .log except the timing fields of the BEST line (cpu_sec/run,
   wall), and the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots=`. 32 of 32 identical =
   REUSE_VALID; anything else = REUSE_INVALID, and the primary gets no verdict (CONTROL_INVALID).
2. Primary, d = Heart kill P46 - G16 per seed, G16 = §775's game of net-0420. A seed counts if both games finished
   rc 0 with all log checks and an env matching the arm (a combat abort is a counted loss); dropped seeds are listed,
   never imputed; more than 20 dropped = INCOMPLETE. Only seeds whose P46 unit was claimed count (a unit directory in
   NEW_ROOT or a claim in CLAIMS_LIST). Gate: tools/sprt_gate.py gainer (d0 0, d1 +2 pp), alpha 0.05, beta 0.05,
   look 64, cap = the analysed seeds (at most 1,024), seeds gap-free in ascending order. PASS = GO, NOT_SHOWN = STOP;
   at CAP the two-sided 95% seed bootstrap of the mean d (10,000 resamples, seed 20261115) decides: GO if its lower
   bound > 0, STOP if the mean d <= 0, else INCONCLUSIVE. The 95% CI is reported in every case.
3. Cost (descriptive): CPU sec per run, P46 / G16, also corrected for machine speed by the sentinel.
4. Secondary (not gates): the nonregression SPRT on the same pairs; P46 - D (§775) with 95% CI; per arm Heart kill,
   act-4 reach (final floor >= 52), mean floor, CPU sec per run, games over 1 h; Act-4 conversion; the primary
   contrast on the first 512 seeds.
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
REPO = HERE.parents[4]
SEEDS = range(111378256, 111379280)
SENTINEL = range(111378256, 111378288)
NEW_ARMS = ("G16", "P46")
REF_ARMS = ("D", "G16", "G32", "G64")
ALPHA = 0.05
MARGIN = 0.03
MAX_DROPPED = 20
KEYS = ("STS_SILVER_GUMBEL_ROOT", "STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", "STS_SILVER_LEARNED_STOP",
        "STS_SILVER_GUMBEL_LEARNED_STOP", "STS_SILVER_GUMBEL_ROOT_UCB", "STS_SILVER_ROOT_PRIOR_WEIGHT",
        "STS_SILVER_TREE_PRIOR_MIN_VISITS", "STS_SILVER_NODE_REUSE_CAP", "STS_SILVER_GUMBEL_STOP_TRACE",
        "STS_SILVER_GUMBEL_ROOT_ROOMS", "STS_SILVER_GUMBEL_ROOT_SIMS", "STS_SILVER_COMBATNET_PRIOR",
        "STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS", "STS_SILVER_COMBATNET_TREE_MIN_VISITS",
        "STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE", "STS_SILVER_PRIOR_PLAYOUT_ELITE", "STS_SILVER_ACT4_HEART_BUDGET")
_G = ("16", "4", "1")
_T = ("400", "8", None, None, None, None, None, None, None, None, "0", None)
_H = ("400", "8", None, None, None, None, None, None, None, None, "0", "24000")
ENV = {"new": {"G16": _G + (None, None) + _T, "P46": _G + (None, None) + _T},
       "ref": {"D": (None, None, "1", None, None) + _T, "G16": _G + (None, None) + _T,
               "G32": _G + (None, None) + _T, "G64": _G + (None, None) + _T}}
NET = {"G16": "net-0420.bin", "P46": "net-0046.bin", "D": "net-0420.bin", "G32": "net-0420.bin",
       "G64": "net-0420.bin"}   # P46 and G16 share the env keys; the loaded net tells them apart
SIMS = {"G16": 16000, "P46": 16000, "D": 10000, "G32": 32000, "G64": 64000}
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
        if env_of(done.with_suffix(".env")) != ENV[side][arm] or not re.search(
                r"^\[heart1\] loaded \S*/" + re.escape(NET[arm]) + " ", log + "\n" + err, re.M):
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


def boot(x, level=95.0, seed=20261115):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    t = (100.0 - level) / 2
    return float(np.percentile(bs, t)), float(np.percentile(bs, 100.0 - t))


def boot_ratio(y, x, seed=20261115):
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
    # PG16H24 PREREG (Evaluation): primary = sprt_gate gainer (d0 0, d1 +2 pp); PASS = GO, NOT_SHOWN = STOP; at CAP
    # the two-sided 95% seed bootstrap decides GO (lower bound > 0) / STOP (mean <= 0) / INCONCLUSIVE.
    sv = r["sprt_gainer"].get("verdict")
    if len(dropped) > MAX_DROPPED:
        v = "INCOMPLETE"
    elif sv == "PASS":
        v = "GO"
    elif sv == "NOT_SHOWN":
        v = "STOP"
    elif sv == "CAP":
        v = "GO" if r["ci95"][0] > 0 else ("STOP" if r["d"] <= 0 else "INCONCLUSIVE")
    else:
        v = "PARTIAL"
    r["verdict"] = v
    r["gainer"] = sv
    r["nonregression"] = r["sprt"].get("verdict")
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


CURVE_LAST = 111378767   # the budget curve's 512 seeds (§778, §779, §781) are 111378256-111378767


def per_arm_on(new, ref, seeds):
    out = {}
    seeds = set(seeds)
    for side, games, arms in (("new", new, NEW_ARMS), ("ref", ref, REF_ARMS)):
        for arm in arms:
            vals = [v for (a, s), v in games.items() if a == arm and s in seeds]
            if not vals:
                continue
            g = np.array(vals, float)
            out[f"{side}:{arm}"] = {"games": len(g), "heart": float(g[:, 0].mean()), "act4": float(g[:, 1].mean()),
                                    "floor": float(g[:, 2].mean()), "cpu_sec": float(g[:, 3].mean())}
    return out


def act4_conversion(new, ref):
    """Heart kills per Act-4 arrival (final floor >= 52) for G16 (§775) and P46, and paired on the seeds where
    both reached Act 4 (descriptive; the Heart's budget is one of the two changes)."""
    res = {}
    for name, games in (("G16", ref), ("P46", new)):
        v = [g for (a, s), g in games.items() if a == name and s in SEEDS and g[1] == 1]
        res[name] = {"arrivals": len(v), "kills": int(sum(g[0] for g in v)),
                     "rate": float(np.mean([g[0] for g in v])) if v else None}
    both = [s for s in SEEDS if ("G16", s) in ref and ("P46", s) in new and ref[("G16", s)][1] == 1
            and new[("P46", s)][1] == 1]
    res["both"] = len(both)
    if both:
        x = np.array([ref[("G16", s)][0] for s in both], float)
        y = np.array([new[("P46", s)][0] for s in both], float)
        res.update(both_G16=float(x.mean()), both_P46=float(y.mean()), both_d=float((y - x).mean()),
                   both_ci95=boot(y - x) if len(both) > 1 else None)
    return res


def main(new_root, ref_root, out, claims=None):
    new, bad_n, ab_n, mm_n, pr_n, attempted = load(new_root, "new", claims)
    ref, bad_r, ab_r, mm_r, pr_r, _ = load(ref_root, "ref")
    outdir = os.path.dirname(out) or "."
    sent = sentinel(new, ref, pr_n, pr_r)
    res = {"bad": bad_n + bad_r, "aborts": ab_n + ab_r, "env_mismatch": mm_n + mm_r, "sentinel": sent}
    p = contrast(new, ref, attempted, ("ref", "G16"), ("new", "P46"), outdir, "P46", gated=True)
    if sent["verdict"] != "REUSE_VALID":
        p["verdict"] = "CONTROL_INVALID"
    if "cpu_speed_new_over_ref" in sent and "cpu_ratio" in p:
        p["cpu_ratio_machine_corrected"] = p["cpu_ratio"] / sent["cpu_speed_new_over_ref"]
    res["primary"] = p
    res["secondary"] = {"P46_minus_D": contrast(new, ref, attempted, ("ref", "D"), ("new", "P46"), outdir,
                                                       "D", False),
                        "P46_minus_G16_first512": contrast(new, ref, {a for a in attempted if int(a.split("_")[0])
                                                                         <= CURVE_LAST}, ("ref", "G16"),
                                                              ("new", "P46"), outdir, "first512", False)}
    res["act4_conversion"] = act4_conversion(new, ref)
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
    res["per_arm_first512"] = {k: v for k, v in per_arm_on(new, ref, range(SEEDS[0], CURVE_LAST + 1)).items()}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"bad {len(res['bad'])} (env mismatch {len(res['env_mismatch'])}) aborts {len(res['aborts'])}  sentinel "
          f"{sent['identical']}/{sent['of']} {sent['verdict']}")
    for name, r in [("P46 - G16", p), ("P46 - D", res["secondary"]["P46_minus_D"]),
                    ("P46 - G16, first 512", res["secondary"]["P46_minus_G16_first512"])]:
        if not r["n"]:
            print(f"{name}: no analysable seed -> {r.get('verdict')}")
            continue
        print(f"{name}: n {r['n']} dropped {len(r['dropped'])}  heart {100 * r['heart_control']:.2f}% -> "
              f"{100 * r['heart_arm']:.2f}%  d {100 * r['d']:+.2f} [{100 * r['ci95'][0]:+.2f}, "
              f"{100 * r['ci95'][1]:+.2f}] pp  act4 d {100 * r['act4_d']:+.2f} pp  cpu ratio {r['cpu_ratio']:.3f}"
              + (f"  sims ratio {r['sims_ratio']:.3f}" if "sims_ratio" in r else "")
              + f"  verdict {r.get('verdict')}"
              + (f" (gainer sprt {r['gainer']}, nonregression {r['nonregression']})" if "sprt" in r else "")
              + (f"  cpu q50/90/99/max {[round(v) for v in r['cpu_quantiles_arm']]}" if "cpu_quantiles_arm" in r else ""))
    c = res["act4_conversion"]
    if c.get("both"):
        print(f"act-4 conversion: G16 {c['G16']['kills']}/{c['G16']['arrivals']}, P46 {c['P46']['kills']}/"
              f"{c['P46']['arrivals']}; both reached on {c['both']} seeds: G16 {100 * c['both_G16']:.1f}% P46 "
              f"{100 * c['both_P46']:.1f}% d {100 * c['both_d']:+.1f} [{100 * c['both_ci95'][0]:+.1f}, "
              f"{100 * c['both_ci95'][1]:+.1f}] pp")
    return res


def self_test():
    """Synthetic campaign: sentinel valid / invalid, drops, an abort, a wrong env -> verdicts."""
    import random
    import shutil
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    newr, refr = os.path.join(t, "new"), os.path.join(t, "ref")
    rate = {"D": 0.30, "G16": 0.40, "G32": 0.40, "G64": 0.40, "P46": 0.40}

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
            f"[heart1] loaded /root/{rng.random()}/{NET[env_arm or arm]} (x)\n[heart1_ppo] seed={s} decisions={k + 3}\n"
            f"[silver] whole-run Gumbel roots=10 sims={sims} (all)\n" + extra)

    outcome = {}
    for s in SEEDS:
        for arm in REF_ARMS:
            outcome[(arm, s)] = int(rng.random() < rate[arm])
            write(refr, "ref", f"{s}_{'G64' if arm == 'G64' else 'low'}", arm, s, outcome[(arm, s)])
        k = outcome[("G16", s)] if rng.random() < 0.8 else int(rng.random() < rate["P46"])
        write(newr, "new", f"{s}_P46", "P46", s, k, rc=1 if s == 111378500 else 0,
              env_arm="G16" if s == 111378600 else None, ab=int(s == 111378700), sims=800)
    for s in SENTINEL:
        write(newr, "new", f"{s}_G16", "G16", s, outcome[("G16", s)])
    r = main(newr, refr, os.path.join(t, "r.json"))
    assert r["sentinel"]["verdict"] == "REUSE_VALID", r["sentinel"]
    p = r["primary"]
    assert p["dropped"] == [111378500, 111378600], p["dropped"]
    assert r["env_mismatch"] == ["new:P46-111378600"], r["env_mismatch"]
    assert r["aborts"] == ["new:P46-111378700"], r["aborts"]
    assert p["verdict"] in ("STOP", "INCONCLUSIVE"), p["verdict"]
    assert abs(p["sims_ratio"] - 0.8) < 1e-9 and abs(p["cpu_ratio"] - 0.8) < 1e-9, p
    f5 = r["secondary"]["P46_minus_G16_first512"]
    assert f5["n"] == 510 and f5["dropped"] == [111378500, 111378600], (f5["n"], f5["dropped"])
    c = r["act4_conversion"]
    assert c["both"] > 0 and c["G16"]["arrivals"] == sum(g[1] for (a_, s_), g in load(refr, "ref")[0].items()
                                                         if a_ == "G16"), c
    assert r["per_arm_first512"]["new:P46"]["games"] == 510, r["per_arm_first512"]["new:P46"]
    # a differing sentinel game (another decision count) -> CONTROL_INVALID
    s0 = SENTINEL[3]
    e = Path(newr, f"{s0}_G16", f"G16-{s0}.err")
    e.write_text(e.read_text().replace("decisions=", "decisions=9"))
    r = main(newr, refr, os.path.join(t, "r2.json"))
    assert r["sentinel"]["differing"] == [s0] and r["primary"]["verdict"] == "CONTROL_INVALID", r["sentinel"]
    e.write_text(e.read_text().replace("decisions=9", "decisions="))
    # a much worse arm -> NOT_SHOWN; a claim-only unit (lost container) is a drop
    for s in SEEDS:
        shutil.rmtree(os.path.join(newr, f"{s}_P46"))
        write(newr, "new", f"{s}_P46", "P46", s, int(rng.random() < 0.25), sims=800)
    shutil.rmtree(os.path.join(newr, "111379000_P46"))
    cl = os.path.join(t, "claims.txt")
    Path(cl).write_text("claims/111379000_P46.a1\nclaims/111379000_P46.a1/hb\nnot-a-claim\n")
    r = main(newr, refr, os.path.join(t, "r3.json"), cl)
    assert r["primary"]["dropped"] == [111379000] and r["primary"]["verdict"] == "STOP", r["primary"]["verdict"]
    # a much better arm -> GO
    for s in SEEDS:
        if s == 111379000:
            continue
        shutil.rmtree(os.path.join(newr, f"{s}_P46"))
        write(newr, "new", f"{s}_P46", "P46", s, int(rng.random() < 0.60), sims=800)
    r = main(newr, refr, os.path.join(t, "r3b.json"), cl)
    assert r["primary"]["verdict"] == "GO" and r["primary"]["gainer"] == "PASS", r["primary"]["verdict"]
    for s in range(111379100, 111379121):
        Path(newr, f"{s}_P46", f"P46-{s}.done").write_text(f"tag=P46-{s} rc=1 start=x wall=1 abort=0")
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
