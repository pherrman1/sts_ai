#!/usr/bin/env python3
"""Whole-run c2 test (PREREG.md): Gumbel tuning stage 2's pick c2 against §775's G16 + mb4 in whole A20 runs with
net-0420 as the out-of-combat policy, seeds 111378256-111379279; then (Test 2) the node reuse cap 262144.

    python3 analyze.py NEW_ROOT REF_ROOT result.json [CLAIMS_LIST]
    python3 analyze.py --self-test

NEW_ROOT holds this campaign's unit directories (<seed>_<SET>/ with ARM-SEED.{done,log,err,env} from run_unit.sh;
verify_campaign.py --extract DIR writes DIR/out/units/<unit>/), REF_ROOT §775's (gumbel_wholerun_20261108, arms D,
G16, G32, G64).
1. Sentinel (ADR-0064): this campaign's G16 games on seeds 111378256-111378287 against §775's G16 games. A game's
   fingerprint is its rc, abort flag, whole .log except the timing fields of the BEST line (cpu_sec/run, wall), and
   the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots=`. 32 of 32 identical = REUSE_VALID;
   anything else = REUSE_INVALID, and no contrast against §775's games gets a verdict (CONTROL_INVALID).
2. Primary, d = Heart kill C2 - G16 per seed, G16 = §775's game. A seed counts if both games finished rc 0 with all
   log checks and an env matching the arm (a combat abort is a counted loss); dropped seeds are listed, never
   imputed; more than 20 dropped = INCOMPLETE. Only seeds whose C2 unit was claimed count (a unit directory in
   NEW_ROOT or a claim in CLAIMS_LIST). Gate: tools/sprt_gate.py gainer, alpha 0.05, beta 0.05, look 64, cap = the
   analysed seeds (at most 1,024), seeds gap-free in ascending order. PASS = GO; NOT_SHOWN = NOT_SHOWN; at CAP the
   (1 - alpha) seed bootstrap of the mean d decides (10,000 resamples, seed 20261109): GO if lo > 0, STOP if
   mean <= 0, else INCONCLUSIVE. The 95% CI is reported in every case.
3. Test 2 (when its games exist): d = C2CAP - C2 (both this campaign) and G16CAP - G16 (§775's), the same gate.
4. Secondary (not gates): C2 - D, C2 - G32 (§775's games) with 95% CIs, each primary's sprt_gate nonregression;
   per arm Heart kill, act-4 reach (final floor >= 52), mean floor, CPU sec per run and its ratio to G16, games over
   1 h, and the tree reuse counters (sum over games: reroots, inherited visits, fresh roots, cap resets and the
   visits they dropped, as shares of reroots and of all simulations).
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
NEW_ARMS = ("C2", "G16", "C2CAP", "G16CAP")
REF_ARMS = ("D", "G16", "G32", "G64")
ALPHA = 0.05
MAX_DROPPED = 20
KEYS = ("STS_SILVER_GUMBEL_ROOT", "STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", "STS_SILVER_LEARNED_STOP",
        "STS_SILVER_GUMBEL_ROOT_UCB", "STS_SILVER_GUMBEL_ROOT_WIDEN_END_TURN", "STS_SILVER_GUMBEL_ROOT_WIDEN_CHANCE",
        "STS_SILVER_ROOT_PRIOR_WEIGHT", "STS_SILVER_TREE_PRIOR_MIN_VISITS", "STS_SILVER_NODE_REUSE_CAP")
_G = ("16", "4", "1")
_C2 = ("12.5", "14.8", "1.85", "100", "32")
ENV = {"new": {"C2": _G + _C2 + (None,), "G16": _G + (None, None, None, "400", "8", None),
               "C2CAP": _G + _C2 + ("262144",), "G16CAP": _G + (None, None, None, "400", "8", "262144")},
       "ref": {"D": (None, None, "1", None, None, None, "400", "8", None),
               "G16": _G + (None, None, None, "400", "8", None), "G32": _G + (None, None, None, "400", "8", None),
               "G64": _G + (None, None, None, "400", "8", None)}}
SIMS = {"C2": 16000, "G16": 16000, "C2CAP": 16000, "G16CAP": 16000, "D": 10000, "G32": 32000, "G64": 64000}
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)
SIMS_LINE = re.compile(r"seeds (\d+)\.\.\d+\s+asc 20\s+sims (\d+) ")
REUSE = re.compile(r"^\[silver\] whole-run tree reuse: reroots=(\d+) inherited=(\d+) fresh=(\d+) cap_resets=(\d+) "
                   r"cap_lost=(\d+) reuse_cap=(\d+)$", re.M)
ROOTS = re.compile(r"^\[silver\] whole-run Gumbel roots=(\d+) sims=(\d+) ", re.M)


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
    """games[(arm, seed)] = (heart, act4, floor, cpu_sec, wall, reuse counters or None, Gumbel sims or None)."""
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
        r, g = REUSE.search(err), ROOTS.search(err)
        floor = float(m.group(2))
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)), int(d["wall"]),
                      tuple(int(x) for x in r.groups()) if r else None, int(g.group(2)) if g else None)
    return games, bad, aborts, mismatch, prints, attempted


def boot(x, level=95.0, seed=20261109):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    t = (100.0 - level) / 2
    return float(np.percentile(bs, t)), float(np.percentile(bs, 100.0 - t))


def gate(pairs, variant, cap, alpha):
    g = subprocess.run([sys.executable, str(REPO / "tools" / "sprt_gate.py"), pairs, "--variant", variant,
                        "--look", "64", "--cap", str(cap), "--alpha", str(alpha), "--beta", "0.05"],
                       capture_output=True, text=True)
    if g.returncode != 0:
        raise RuntimeError(f"sprt_gate failed: {g.stderr.strip()}")
    return json.loads(g.stdout)


def pair_games(new, ref, a, b):
    """Games of arm a (control) and b on each seed: (side, arm) pairs."""
    src = {"new": new, "ref": ref}
    seeds = [s for s in SEEDS if (a[1], s) in src[a[0]] and (b[1], s) in src[b[0]]]
    x = np.array([src[a[0]][(a[1], s)][:5] for s in seeds], float).reshape(-1, 5)
    y = np.array([src[b[0]][(b[1], s)][:5] for s in seeds], float).reshape(-1, 5)
    return seeds, x, y


def contrast(new, ref, attempted, a, b, outdir, name, gated=True):
    seeds, x, y = pair_games(new, ref, a, b)
    universe = [s for s in SEEDS if f"{s}_{b[1]}" in attempted]
    have = set(seeds)
    seeds_u = [s for s in universe if s in have]
    idx = [seeds.index(s) for s in seeds_u]
    x, y = x[idx], y[idx]
    dropped = [s for s in universe if s not in have]
    r = {"control": f"{a[0]}:{a[1]}", "arm": f"{b[0]}:{b[1]}", "n": len(seeds_u), "dropped": dropped}
    if not seeds_u:
        r["verdict"] = "INCOMPLETE" if gated else None
        return r
    d = y[:, 0] - x[:, 0]
    r.update({"heart_control": float(x[:, 0].mean()), "heart_arm": float(y[:, 0].mean()), "d": float(d.mean()),
              "ci95": boot(d), "act4_d": float((y[:, 1] - x[:, 1]).mean()), "act4_ci95": boot(y[:, 1] - x[:, 1]),
              "floor_d": float((y[:, 2] - x[:, 2]).mean()), "floor_ci95": boot(y[:, 2] - x[:, 2]),
              "cpu_ratio": float(y[:, 3].mean() / x[:, 3].mean()),
              "arm_only": int((d > 0).sum()), "control_only": int((d < 0).sum())})
    if not gated:
        return r
    loa, hia = boot(d, 100.0 * (1 - ALPHA))
    pairs = os.path.join(outdir, f"pairs_{name}.csv")
    with open(pairs, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key", "a", "b"])
        for k, (p, q) in enumerate(zip(x[:, 0], y[:, 0])):
            w.writerow([k, int(p), int(q)])
    cap = min(1024, len(seeds_u))
    r["ci_alpha"] = [loa, hia]
    r["sprt"] = gate(pairs, "gainer", cap, ALPHA)
    r["sprt_nonregression"] = gate(pairs, "nonregression", cap, 0.05)
    sv = r["sprt"].get("verdict")
    if len(dropped) > MAX_DROPPED:
        v = "INCOMPLETE"
    elif sv == "PASS":
        v = "GO"
    elif sv == "NOT_SHOWN":
        v = "NOT_SHOWN"
    elif sv == "CAP":
        v = "GO" if loa > 0 else ("STOP" if d.mean() <= 0 else "INCONCLUSIVE")
    else:
        v = "PARTIAL"
    r["verdict"] = v
    r["nonregression"] = r["sprt_nonregression"].get("verdict")
    return r


def sentinel(new_prints, ref_prints):
    rows = []
    for s in SENTINEL:
        a, b = new_prints.get(("G16", s)), ref_prints.get(("G16", s))
        rows.append({"seed": s, "present": a is not None and b is not None, "identical": a is not None and a == b})
    same = sum(r["identical"] for r in rows)
    return {"identical": same, "of": len(rows), "differing": [r["seed"] for r in rows if not r["identical"]],
            "verdict": "REUSE_VALID" if same == len(rows) else "REUSE_INVALID"}


def main(new_root, ref_root, out, claims=None):
    new, bad_n, ab_n, mm_n, pr_n, attempted = load(new_root, "new", claims)
    ref, bad_r, ab_r, mm_r, pr_r, _ = load(ref_root, "ref")
    outdir = os.path.dirname(out) or "."
    sent = sentinel(pr_n, pr_r)
    valid = sent["verdict"] == "REUSE_VALID"
    res = {"bad": bad_n + bad_r, "aborts": ab_n + ab_r, "env_mismatch": mm_n + mm_r, "sentinel": sent}
    res["primary"] = contrast(new, ref, attempted, ("ref", "G16"), ("new", "C2"), outdir, "C2", gated=True)
    if not valid:
        res["primary"]["verdict"] = "CONTROL_INVALID"
    test2 = {}
    if any(k[0] == "C2CAP" for k in new):
        test2["C2CAP"] = contrast(new, ref, attempted, ("new", "C2"), ("new", "C2CAP"), outdir, "C2CAP")
    if any(k[0] == "G16CAP" for k in new):
        test2["G16CAP"] = contrast(new, ref, attempted, ("ref", "G16"), ("new", "G16CAP"), outdir, "G16CAP")
        if not valid:
            test2["G16CAP"]["verdict"] = "CONTROL_INVALID"
    res["test2"] = test2
    res["secondary"] = {f"C2_minus_{a}": contrast(new, ref, attempted, ("ref", a), ("new", "C2"), outdir, a, False)
                        for a in ("D", "G32")}
    per_arm = {}
    g16cpu = np.mean([v[3] for (a, s), v in ref.items() if a == "G16"]) if any(a == "G16" for a, _ in ref) else None
    for side, games, arms in (("new", new, NEW_ARMS), ("ref", ref, REF_ARMS)):
        for arm in arms:
            vals = [v for (a, s), v in games.items() if a == arm and s in SEEDS]
            if not vals:
                continue
            g = np.array([v[:5] for v in vals], float)
            row = {"games": len(g), "heart": float(g[:, 0].mean()), "act4": float(g[:, 1].mean()),
                   "floor": float(g[:, 2].mean()), "cpu_sec": float(g[:, 3].mean()),
                   "cpu_ratio_to_ref_G16": float(g[:, 3].mean() / g16cpu) if g16cpu else None,
                   "long_games": int((g[:, 4] > 3600).sum()), "max_wall": int(g[:, 4].max())}
            ru = [v[5] for v in vals if v[5] is not None]
            sims = sum(v[6] for v in vals if v[5] is not None and v[6] is not None)
            if ru:
                t = np.array(ru, np.int64).sum(0)
                rer, inh, fresh, caps, lost = (int(t[i]) for i in range(5))
                row["reuse"] = {"games": len(ru), "reroots": rer, "inherited": inh, "fresh": fresh,
                                "cap_resets": caps, "cap_lost": lost,
                                "cap_reset_share_of_kept_or_reset": caps / (rer + caps) if rer + caps else None,
                                "cap_lost_share_of_sims": lost / sims if sims else None,
                                "inherited_share_of_sims": inh / sims if sims else None}
            per_arm[f"{side}:{arm}"] = row
    res["per_arm"] = per_arm
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"bad {len(res['bad'])} (env mismatch {len(res['env_mismatch'])}) aborts {len(res['aborts'])}  sentinel "
          f"{sent['identical']}/{sent['of']} {sent['verdict']}")
    for name, r in [("C2 - G16", res["primary"])] + [(f"{k} test 2", v) for k, v in test2.items()] + \
            [(k, v) for k, v in res["secondary"].items()]:
        if not r["n"]:
            print(f"{name}: no analysable seed -> {r.get('verdict')}")
            continue
        print(f"{name}: n {r['n']} dropped {len(r['dropped'])}  heart {100 * r['heart_control']:.2f}% -> "
              f"{100 * r['heart_arm']:.2f}%  d {100 * r['d']:+.2f} [{100 * r['ci95'][0]:+.2f}, "
              f"{100 * r['ci95'][1]:+.2f}] pp  act4 d {100 * r['act4_d']:+.2f} pp  floor d {r['floor_d']:+.2f}  "
              f"cpu ratio {r['cpu_ratio']:.2f}  verdict {r.get('verdict')}"
              + (f" (sprt {r['sprt'].get('verdict')}), nonregression {r['nonregression']}" if "sprt" in r else ""))
    for k, row in per_arm.items():
        if "reuse" in row:
            u = row["reuse"]
            print(f"{k} reuse: {u['games']} games  cap resets {u['cap_resets']} of {u['reroots'] + u['cap_resets']} "
                  f"kept-or-reset reroots ({100 * (u['cap_reset_share_of_kept_or_reset'] or 0):.2f}%), lost "
                  f"{100 * (u['cap_lost_share_of_sims'] or 0):.2f}% of sims, carried "
                  f"{100 * (u['inherited_share_of_sims'] or 0):.2f}%")
    return res


def self_test():
    """Synthetic campaign: sentinel valid / invalid, drops, an abort, a wrong env, test-2 arms -> verdicts."""
    import random
    import shutil
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    newr, refr = os.path.join(t, "new"), os.path.join(t, "ref")
    rate = {"D": 0.30, "G16": 0.40, "G32": 0.40, "G64": 0.40, "C2": 0.48, "C2CAP": 0.48, "G16CAP": 0.40}

    def write(root, side, unit, arm, s, k, rc=0, ab=0, env_arm=None, extra=""):
        dd = os.path.join(root, unit)
        os.makedirs(dd, exist_ok=True)
        Path(dd, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=20 abort={ab}")
        Path(dd, f"{arm}-{s}.env").write_text("STS_FAIR=1\n" + "".join(
            f"{k_}={v}\n" for k_, v in zip(KEYS, ENV[side][env_arm or arm]) if v is not None))
        Path(dd, f"{arm}-{s}.log").write_text(
            f"BEST stack config: x  seeds {s}..{s}  asc 20  sims {SIMS[arm]}  threads 1\n"
            f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  avg_hp_end= 0.0   "
            f"cpu_sec/run={rng.uniform(10, 30):.2f}   wall={rng.uniform(10, 30):.1f}s\n")
        Path(dd, f"{arm}-{s}.err").write_text(
            f"[heart1] loaded /root/{rng.random()}/net-0420.bin (x)\n[heart1_ppo] seed={s} decisions={k + 3}\n"
            f"[silver] whole-run Gumbel roots=10 sims=1000 (all)\n" + extra)

    reuse = "[silver] whole-run tree reuse: reroots=8 inherited=400 fresh=2 cap_resets=1 cap_lost=50 reuse_cap=32768\n"
    outcome = {}
    for s in SEEDS:
        for arm in REF_ARMS:
            outcome[(arm, s)] = int(rng.random() < rate[arm])
            write(refr, "ref", f"{s}_{'G64' if arm == 'G64' else 'low'}", arm, s, outcome[(arm, s)])
        c2 = int(rng.random() < rate["C2"])
        write(newr, "new", f"{s}_C2", "C2", s, c2, rc=1 if s == 111378500 else 0,
              env_arm="G16" if s == 111378600 else None, ab=int(s == 111378700), extra=reuse)
    for s in SENTINEL:
        write(newr, "new", f"{s}_G16", "G16", s, outcome[("G16", s)], extra=reuse)
    r = main(newr, refr, os.path.join(t, "r.json"))
    assert r["sentinel"]["verdict"] == "REUSE_VALID", r["sentinel"]
    p = r["primary"]
    assert p["dropped"] == [111378500, 111378600], p["dropped"]
    assert r["env_mismatch"] == ["new:C2-111378600"], r["env_mismatch"]
    assert r["aborts"] == ["new:C2-111378700"], r["aborts"]
    assert p["verdict"] == "GO", p["verdict"]   # +8 pp synthetic gain
    assert r["per_arm"]["new:C2"]["reuse"]["cap_resets"] == 1022, r["per_arm"]["new:C2"]["reuse"]
    assert r["test2"] == {}
    # a differing sentinel game (another decision count) -> CONTROL_INVALID
    s0 = SENTINEL[3]
    e = Path(newr, f"{s0}_G16", f"G16-{s0}.err")
    e.write_text(e.read_text().replace("decisions=", "decisions=9"))
    r = main(newr, refr, os.path.join(t, "r2.json"))
    assert r["sentinel"]["differing"] == [s0] and r["primary"]["verdict"] == "CONTROL_INVALID", r["sentinel"]
    e.write_text(e.read_text().replace("decisions=9", "decisions="))
    # test 2 arms, no gain; a claim-only C2CAP unit (lost container) is a drop of test 2 only
    for s in SEEDS:
        write(newr, "new", f"{s}_C2CAP", "C2CAP", s, int(rng.random() < rate["C2CAP"]), extra=reuse)
    shutil.rmtree(os.path.join(newr, "111379000_C2CAP"))
    cl = os.path.join(t, "claims.txt")
    Path(cl).write_text("claims/111379000_C2CAP.a1\nclaims/111379000_C2CAP.a1/hb\nnot-a-claim\n")
    r = main(newr, refr, os.path.join(t, "r3.json"), cl)
    c = r["test2"]["C2CAP"]
    assert c["dropped"] == [111378500, 111378600, 111379000], c["dropped"]
    assert c["verdict"] in ("NOT_SHOWN", "INCONCLUSIVE", "STOP"), c["verdict"]
    assert r["primary"]["verdict"] == "GO" and r["sentinel"]["verdict"] == "REUSE_VALID"
    for s in range(111379100, 111379121):
        Path(newr, f"{s}_C2", f"C2-{s}.done").write_text(f"tag=C2-{s} rc=1 start=x wall=1 abort=0")
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
