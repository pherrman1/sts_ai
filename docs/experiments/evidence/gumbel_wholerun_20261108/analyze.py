#!/usr/bin/env python3
"""Whole-run Gumbel teacher test (PREREG.md): net-0420 policy alone, combat arms D (today's A20 default) and
G16 / G32 / G64 (Gumbel root k 16 + max backup 4 at 16k / 32k / 64k simulations in every fight), seeds
111378256-111379279, every arm on every seed.

    python3 analyze.py OUT_ROOT result.json [CLAIMS_LIST]
    python3 analyze.py --self-test

OUT_ROOT holds one directory per unit (<seed>_<arm>/) with ARM-SEED.{done,log,err,env} from run_unit.sh
(verify_campaign.py --extract DIR writes DIR/out/units/<unit>/).
1. Primary, three contrasts X - D for X in (G16, G32, G64): d = Heart kill X - D per seed. A seed counts for a contrast
   if both games finished rc 0 with all log checks and an ARM-SEED.env whose Gumbel flags match the arm (a combat abort
   is a counted loss, listed); dropped seeds are listed, never imputed; more than 20 dropped seeds in a contrast =
   INCOMPLETE. Only seeds whose units for the contrast were all claimed count (universe(); early stop, PREREG). The gate per contrast (tools/sprt_gate.py gainer, alpha 0.05/3 = Bonferroni over the three contrasts,
   beta 0.05, look 64, cap = number of analysed seeds, at most 1,024) gets the seeds gap-free (key = rank in ascending
   seed order). PASS = GO; NOT_SHOWN = NOT_SHOWN; at CAP the (1 - alpha) seed bootstrap of the mean d decides (10,000
   resamples, seed 20261108): GO if lo > 0, STOP if mean <= 0, else INCONCLUSIVE. The 95% CI is reported in every case.
2. Secondary (not a gate): G32 - G16, G64 - G32 with 95% CIs; each contrast's sprt_gate nonregression.
3. Descriptive per arm: Heart kill, act-4 reach (final floor >= 52), mean floor, cpu_sec/run and ratio to D, combat
   aborts, games with wall > 3,600 s.
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
ARMS = ("D", "G16", "G32", "G64")
CONTRASTS = ("G16", "G32", "G64")
ALPHA = 0.05 / 3
MAX_DROPPED = 20
KEYS = ("STS_SILVER_GUMBEL_ROOT", "STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", "STS_SILVER_LEARNED_STOP")
ENV = {"D": (None, None, "1"), "G16": ("16", "4", "1"), "G32": ("16", "4", "1"), "G64": ("16", "4", "1")}
SIMS = {"D": 10000, "G16": 16000, "G32": 32000, "G64": 64000}
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)
SIMS_LINE = re.compile(r"seeds (\d+)\.\.\d+\s+asc 20\s+sims (\d+) ")


def env_of(path):
    if not path.exists():
        return None
    env = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return tuple(env.get(k) for k in KEYS)


ATTEMPTED = set()   # unit ids (<seed>_low, <seed>_G64) that were claimed: a unit directory or a claim in CLAIMS_LIST
UNIT_OF = {"D": "low", "G16": "low", "G32": "low", "G64": "G64"}


def load(root, claims=None):
    games, bad, aborts, mismatch = {}, [], [], []
    ATTEMPTED.clear()
    ATTEMPTED.update(p.name for p in Path(root).iterdir() if p.is_dir()) if Path(root).is_dir() else None
    if claims:
        for line in Path(claims).read_text().split():
            m = re.match(r"^(\d+_(?:low|G64))\.a\d+$", line.strip().rstrip("/"))
            if m:
                ATTEMPTED.add(m.group(1))
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if arm not in ARMS:
            raise ValueError(f"unknown arm in {d['tag']}")
        log = done.with_suffix(".log").read_text() if done.with_suffix(".log").exists() else ""
        m = WIN.search(log) if d["rc"] == "0" else None
        s = SIMS_LINE.search(log)
        if not m or not s or int(s.group(2)) != SIMS[arm] or int(s.group(1)) != int(seed):
            bad.append(d["tag"])
            continue
        if env_of(done.with_suffix(".env")) != ENV[arm]:
            mismatch.append(d["tag"])
            bad.append(d["tag"])
            continue
        key = (arm, int(seed))
        if key in games:
            raise ValueError(f"{d['tag']} twice")
        if d.get("abort") == "1":
            aborts.append(d["tag"])
        floor = float(m.group(2))
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)), int(d["wall"]))
    return games, sorted(bad), sorted(aborts), sorted(mismatch)


def boot(x, level=95.0, seed=20261108):
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


def universe(arms):
    """The pre-registered seeds whose units for `arms` were all claimed (PREREG "Stopping"): a unit counts as claimed
    if it has a unit directory in OUT_ROOT or a claim directory in CLAIMS_LIST (a snapshot of the share's claims/ after
    every worker finished). Whether a unit is claimed is fixed before any of its games ends, so a stop that leaves a
    seed's other unit unclaimed removes the seed without selecting on outcomes; a claimed unit without its games
    (failed 4 times, rc != 0, bad checks) is a drop."""
    need = {UNIT_OF[a] for a in arms}
    return [s for s in SEEDS if all(f"{s}_{u}" in ATTEMPTED for u in need)]


def paired(games, a_arm, b_arm):
    seeds = [s for s in universe((a_arm, b_arm)) if (a_arm, s) in games and (b_arm, s) in games]
    a = np.array([games[(a_arm, s)] for s in seeds], float).reshape(-1, 5)
    b = np.array([games[(b_arm, s)] for s in seeds], float).reshape(-1, 5)
    return seeds, a, b


def contrast(games, arm, outdir):
    seeds, a, b = paired(games, "D", arm)
    dropped = [s for s in universe(("D", arm)) if s not in set(seeds)]
    if not seeds:
        return {"n": 0, "dropped": dropped, "verdict": "INCOMPLETE", "nonregression": None}
    d = b[:, 0] - a[:, 0]
    lo95, hi95 = boot(d)
    loa, hia = boot(d, 100.0 * (1 - ALPHA))
    pairs = os.path.join(outdir, f"pairs_{arm}.csv")
    with open(pairs, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key", "a", "b"])
        for k, (x, y) in enumerate(zip(a[:, 0], b[:, 0])):
            w.writerow([k, int(x), int(y)])
    cap = min(1024, len(seeds))
    r = {"n": len(seeds), "dropped": dropped, "heart_D": a[:, 0].mean(), "heart_X": b[:, 0].mean(),
         "d": d.mean(), "ci95": [lo95, hi95], "ci_alpha": [loa, hia],
         "act4_d": float((b[:, 1] - a[:, 1]).mean()), "act4_ci95": boot(b[:, 1] - a[:, 1]),
         "floor_d": float((b[:, 2] - a[:, 2]).mean()), "floor_ci95": boot(b[:, 2] - a[:, 2]),
         "cpu_ratio": b[:, 3].mean() / a[:, 3].mean(),
         "sprt": gate(pairs, "gainer", cap, ALPHA), "sprt_nonregression": gate(pairs, "nonregression", cap, 0.05)}
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


def main(root, out, claims=None):
    games, bad, aborts, mismatch = load(root, claims)
    outdir = os.path.dirname(out) or "."
    res = {"bad": bad, "aborts": aborts, "env_mismatch": mismatch,
           "contrasts": {arm: contrast(games, arm, outdir) for arm in CONTRASTS}}
    for lo_arm, hi_arm in (("G16", "G32"), ("G32", "G64")):
        seeds, a, b = paired(games, lo_arm, hi_arm)
        x = b[:, 0] - a[:, 0]
        res[f"{hi_arm}_minus_{lo_arm}"] = {"n": len(seeds), "d": float(x.mean()) if len(x) else None,
                                           "ci95": boot(x) if len(x) else [None, None]}
    per_arm = {}
    for arm in ARMS:
        g = np.array([v for (a_, s), v in games.items() if a_ == arm and s in SEEDS], float)
        if not len(g):
            continue
        per_arm[arm] = {"games": len(g), "heart": float(g[:, 0].mean()), "act4": float(g[:, 1].mean()),
                        "floor": float(g[:, 2].mean()), "cpu_sec": float(g[:, 3].mean()),
                        "long_games": int((g[:, 4] > 3600).sum()), "max_wall": int(g[:, 4].max())}
    res["per_arm"] = per_arm
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"bad {len(bad)} (env mismatch {len(mismatch)}) aborts {len(aborts)}")
    for arm, r in res["contrasts"].items():
        if not r["n"]:
            print(f"{arm} - D: no analysable seed -> {r['verdict']}")
            continue
        print(f"{arm} - D: n {r['n']} dropped {len(r['dropped'])}  heart D {100 * r['heart_D']:.2f}% "
              f"{arm} {100 * r['heart_X']:.2f}%  d {100 * r['d']:+.2f} [{100 * r['ci95'][0]:+.2f}, "
              f"{100 * r['ci95'][1]:+.2f}] pp  act4 d {100 * r['act4_d']:+.2f} pp  floor d {r['floor_d']:+.2f}  "
              f"cpu ratio {r['cpu_ratio']:.2f}  verdict {r['verdict']} (sprt {r['sprt'].get('verdict')}), "
              f"nonregression {r['nonregression']}")
    for k in ("G32_minus_G16", "G64_minus_G32"):
        p = res[k]
        if p["n"]:
            print(f"{k}: n {p['n']} d {100 * p['d']:+.2f} [{100 * p['ci95'][0]:+.2f}, {100 * p['ci95'][1]:+.2f}] pp")
    return res


def self_test():
    """Synthetic campaign: drops, an abort, a wrong .env and a wrong sims line -> verdicts; 21 drops -> INCOMPLETE."""
    import random
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    root = os.path.join(t, "units")
    drop = {111378500: "G16", 111379000: "G64"}
    rate = {"D": 0.25, "G16": 0.25, "G32": 0.29, "G64": 0.33}
    for s in SEEDS:
        for arm in ARMS:
            dd = os.path.join(root, f"{s}_{UNIT_OF[arm]}")
            os.makedirs(dd, exist_ok=True)
            k = int(rng.random() < rate[arm])
            rc = 1 if drop.get(s) == arm else 0
            ab = int(s == 111378700 and arm == "G32")
            k = k and not ab
            Path(dd, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=20 abort={ab}")
            env_arm = "D" if (s == 111378600 and arm == "G32") else arm
            Path(dd, f"{arm}-{s}.env").write_text("STS_FAIR=1\n" + "".join(
                f"{k_}={v}\n" for k_, v in zip(KEYS, ENV[env_arm]) if v is not None))
            sims = 16000 if (s == 111378800 and arm == "G64") else SIMS[arm]
            Path(dd, f"{arm}-{s}.log").write_text(
                f"BEST stack config: x  seeds {s}..{s}  asc 20  sims {sims}  threads 1\n"
                f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  x cpu_sec/run= 20.0\n")
    r = main(root, os.path.join(t, "r.json"))
    assert r["contrasts"]["G16"]["dropped"] == [111378500], r["contrasts"]["G16"]["dropped"]
    assert r["contrasts"]["G32"]["dropped"] == [111378600], r["contrasts"]["G32"]["dropped"]
    assert r["contrasts"]["G64"]["dropped"] == [111378800, 111379000], r["contrasts"]["G64"]["dropped"]
    assert r["env_mismatch"] == ["G32-111378600"], r["env_mismatch"]
    assert r["aborts"] == ["G32-111378700"], r["aborts"]
    for arm in CONTRASTS:
        c = r["contrasts"][arm]
        assert c["sprt"]["pairs"]["gap_after"] is None and c["verdict"] in ("GO", "NOT_SHOWN", "STOP", "INCONCLUSIVE")
    assert r["contrasts"]["G64"]["verdict"] == "GO", r["contrasts"]["G64"]["verdict"]   # +8 pp synthetic gain
    assert r["contrasts"]["G16"]["verdict"] != "GO", r["contrasts"]["G16"]["verdict"]   # no synthetic gain
    for s in range(111379100, 111379120):
        Path(root, f"{s}_low", f"D-{s}.done").write_text(f"tag=D-{s} rc=1 start=x wall=1 abort=0")
    r = main(root, os.path.join(t, "r2.json"))
    for arm in CONTRASTS:
        assert r["contrasts"][arm]["verdict"] == "INCOMPLETE", (arm, r["contrasts"][arm]["verdict"])
    stop = os.path.join(t, "stopped")   # early stop: many seeds with only one of their two units claimed
    srng = random.Random(7)
    partial, failed = [], 111378300
    for s in range(111378256, 111378701):
        units = {"low", "G64"}
        if s > 111378400 and srng.random() < 0.3:
            units = {srng.choice(["low", "G64"])}
            partial.append(s)
        for u in units:
            dd = os.path.join(stop, f"{s}_{u}")
            os.makedirs(dd)
            if s == failed and u == "G64":
                continue   # claimed and present as a directory, but its game never finished: a drop
            for arm in ([a_ for a_ in ARMS if UNIT_OF[a_] == u]):
                Path(dd, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc=0 start=x wall=20 abort=0")
                Path(dd, f"{arm}-{s}.env").write_text("".join(
                    f"{k_}={v}\n" for k_, v in zip(KEYS, ENV[arm]) if v is not None))
                Path(dd, f"{arm}-{s}.log").write_text(
                    f"BEST stack config: x  seeds {s}..{s}  asc 20  sims {SIMS[arm]}  threads 1\n"
                    f"BEST  win%= 0.0  avg_floor= 30  x cpu_sec/run= 20.0\n")
    # a G64 unit that failed 4 times: no directory, only claims
    lost = next(s for s in range(111378256, 111378400) if s != failed)
    import shutil
    shutil.rmtree(os.path.join(stop, f"{lost}_G64"))
    cl = os.path.join(t, "claims.txt")
    Path(cl).write_text("\n".join(f"{lost}_G64.a{i}" for i in range(1, 5)) + "\nnot-a-claim\n")
    assert len(partial) > 20
    r = main(stop, os.path.join(t, "r4.json"), cl)
    c64, c16 = r["contrasts"]["G64"], r["contrasts"]["G16"]
    assert c64["dropped"] == sorted([failed, lost]), c64["dropped"]
    assert c16["dropped"] == [], c16["dropped"]
    assert c64["verdict"] != "INCOMPLETE" and c16["verdict"] != "INCOMPLETE", (c64["verdict"], c16["verdict"])
    assert c64["n"] == 445 - len(partial) - 2, c64["n"]
    r5 = main(stop, os.path.join(t, "r5.json"))   # without the claims snapshot the lost unit's seed is not counted
    assert r5["contrasts"]["G64"]["dropped"] == [failed], r5["contrasts"]["G64"]["dropped"]
    empty = os.path.join(t, "empty")
    os.makedirs(empty)
    r = main(empty, os.path.join(t, "r3.json"))
    assert all(r["contrasts"][a]["verdict"] == "INCOMPLETE" for a in CONTRASTS)
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:4])
