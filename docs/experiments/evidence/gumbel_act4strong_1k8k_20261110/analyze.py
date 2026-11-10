#!/usr/bin/env python3
"""Act-4-strong budget curve in whole runs (PREREG.md): G1S, G2S, G4S, G8S against G1-G8 and §775's G16 + mb4.

usage: python3 -I analyze.py UNITS_DIR UNITS_1K_DIR UNITS_2K8K_DIR REF_UNITS_DIR OUT.json | --self-test
  UNITS_DIR: this campaign's extracted out/units (G1S, G2S, G4S, G8S); UNITS_1K_DIR: the 1k test's (B1, G1);
  UNITS_2K8K_DIR: the budget curve's (G2, G4, G8); REF_UNITS_DIR: §775's (D, G16, G32, G64), read with
  ../gumbel_tuning_20261109/wholerun/analyze.py's loader.

A game counts if its .done has rc 0, the log has the BEST line with its seed and sims, and its .env has the arm's
values (under the 1k test's KEYS); otherwise it is a drop. Each contrast uses the seeds where both of its games count.
Act 4 reached = final floor >= 52, as in the 1k test.
Primary (five contrasts, Heart kill, paired by seed, seed bootstrap 10,000 resamples seed 20261109, 99% = Bonferroni
over five): GkS - Gk for k = 1, 2, 4, 8 (GkS_BETTER if lo > 0, GkS_WORSE if hi < 0, else NO_DIFFERENCE_SHOWN) and
G16 - G8S (G16_BETTER / G16_WORSE / NO_DIFFERENCE_SHOWN). Every verdict NOT_EVALUABLE if more than 10 of this
campaign's seeds have a drop.
Replay check: for every seed where both games of GkS and Gk count, a Gk game that ended before Act 4 must be equal in
GkS (Heart, final floor, the [heart1_ppo] game line, the Gumbel roots line and the tree reuse line), and a Gk game
that reached Act 4 must reach it in GkS. REPLAY_OK if no seed fails, else REPLAY_BROKEN with the failing tags.
Secondary (95%): G2S - G1S, G4S - G2S, G8S - G4S, G16 - G8S, G32 - G16, G64 - G32, GkS - D, GkS - B1; Heart per
Act-4 arrival of Gk and GkS on the seeds where Gk reached Act 4; per arm Heart, Act-4 reach, final floor, CPU per
run, aborts; Gumbel roots and simulations per run.
"""
import importlib.util, json, re, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


K1 = module(HERE.parent / "gumbel_1k_wholerun_20261109" / "analyze.py", "g1k")
SEEDS = K1.SEEDS
KS = (1, 2, 4, 8)
NEW = {f"G{k}S": 1000 * k for k in KS}
OLD = {f"G{k}": 1000 * k for k in KS}
ENV_NEW = ("16", "4", "1", None, "400", "8", "0", "0", None, None)
ENV_OLD = K1.ENV["G1"]
MAX_DROPPED = 10
LEVEL = 99.0
GAME = re.compile(r"^\[heart1_ppo\] seed=\d+ .*$", re.M)
ROOTS_LINE = re.compile(r"^\[silver\] whole-run Gumbel roots=.*$", re.M)
REUSE_LINE = re.compile(r"^\[silver\] whole-run tree reuse: .*$", re.M)
assert len(K1.KEYS) == len(ENV_NEW) and K1.KEYS[2] == "STS_SILVER_LEARNED_STOP" and K1.KEYS[3] == "STS_SILVER_ACT4_STRONG"


def load_arms(root, arms, env, skip=()):
    """games[(arm, seed)] = (heart, act4, floor, cpu, abort, roots, sims, replay key); drops; seen.
    Arms in `skip` are left out (the 1k test's B1, read with the 1k loader)."""
    games, drops, seen = {}, [], set()
    for done in sorted(Path(root).glob("*/*.done")):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if arm in skip:
            continue
        if arm not in arms:
            raise ValueError(f"unknown arm in {d['tag']}")
        if (arm, int(seed)) in seen:
            raise ValueError(f"{d['tag']} twice")
        seen.add((arm, int(seed)))
        log = done.with_suffix(".log").read_text() if done.with_suffix(".log").exists() else ""
        err = done.with_suffix(".err").read_text() if done.with_suffix(".err").exists() else ""
        m = K1.WIN.search(log) if d["rc"] == "0" else None
        s = K1.SIMS_LINE.search(log)
        if (not m or not s or int(s.group(2)) != arms[arm] or int(s.group(1)) != int(seed)
                or K1.env_of(done.with_suffix(".env")) != env):
            drops.append(d["tag"])
            continue
        g = K1.ROOTS.search(err)
        both = log + "\n" + err
        key = tuple(x.group(0) if x else None for x in (GAME.search(both), ROOTS_LINE.search(err), REUSE_LINE.search(err)))
        floor = float(m.group(2))
        games[(arm, int(seed))] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)),
                                   int(d.get("abort", "0")), int(g.group(1)) if g else None,
                                   int(g.group(2)) if g else None, key)
    return games, drops, seen


def boot_level(x, level, seed=20261109):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    t = (100.0 - level) / 2
    return [float(np.percentile(bs, t)), float(np.percentile(bs, 100.0 - t))]


def replay(old, new):
    """Seeds whose Gk game is not reproduced by GkS before Act 4 (tags)."""
    bad = []
    for s in SEEDS:
        if s not in old or s not in new:
            continue
        a, b = old[s], new[s]
        if a[1] == 0:
            if (a[0], a[2], a[7]) != (b[0], b[2], b[7]) or None in a[7]:
                bad.append(s)
        elif b[1] == 0:
            bad.append(s)
    return bad


def conversion(old, new):
    s = [x for x in SEEDS if x in old and x in new and old[x][1] == 1]
    if not s:
        return dict(seeds=0)
    a = np.array([old[k][0] for k in s], float) * 100
    b = np.array([new[k][0] for k in s], float) * 100
    return dict(seeds=len(s), old=float(a.mean()), new=float(b.mean()), diff_pp=float((b - a).mean()),
                ci95=K1.boot(b - a))


def verdict(c, name, evaluable, seeds):
    if not c.get("seeds"):
        c["verdict"] = "NOT_EVALUABLE"
        return c
    a, b = seeds
    x = np.array([b[k][0] - a[k][0] for k in SEEDS if k in a and k in b], float) * 100
    c["heart_pp_ci_bonferroni"] = boot_level(x, LEVEL)
    lo, hi = c["heart_pp_ci_bonferroni"]
    c["verdict"] = ("NOT_EVALUABLE" if not evaluable else f"{name}_BETTER" if lo > 0 else f"{name}_WORSE" if hi < 0
                    else "NO_DIFFERENCE_SHOWN")
    return c


def analyze(new, drops, seen, old, b1=None, ref=None):
    arm = {a: {s: v for (b, s), v in new.items() if b == a} for a in NEW}
    arm.update({a: {s: v for (b, s), v in old.items() if b == a} for a in OLD})
    if b1 is not None:
        arm["B1"] = {s: v for (b, s), v in b1.items() if b == "B1"}
    if ref is not None:
        arm.update({a: {s: tuple(v[:4]) + (0,) for (b, s), v in ref.items() if b == a} for a in ("D", "G16", "G32", "G64")})
    dropped = sorted({int(t.rsplit("-", 1)[1]) for t in drops} | {s for s in SEEDS if any((a, s) not in seen for a in NEW)})
    evaluable = len(dropped) <= MAX_DROPPED
    L = list(SEEDS)
    prim = {}
    for k in KS:
        o, n = arm[f"G{k}"], arm[f"G{k}S"]
        prim[f"G{k}S - G{k}"] = verdict(K1.contrast(o, n, L), f"G{k}S", evaluable, (o, n))
    if arm.get("G16"):
        prim["G16 - G8S"] = verdict(K1.contrast(arm["G8S"], arm["G16"], L), "G16", evaluable, (arm["G8S"], arm["G16"]))
    sec = {}
    for x, y in (("G1S", "G2S"), ("G2S", "G4S"), ("G4S", "G8S"), ("G8S", "G16"), ("G16", "G32"), ("G32", "G64")):
        if arm.get(x) and arm.get(y):
            sec[f"{y} - {x}"] = K1.contrast(arm[x], arm[y], L)
    for a in NEW:
        for b in ("D", "B1"):
            if arm.get(b):
                sec[f"{a} - {b}"] = K1.contrast(arm[b], arm[a], L)
    rep = {f"G{k}S": [f"G{k}S-{s}" for s in replay(arm[f"G{k}"], arm[f"G{k}S"])] for k in KS}
    checked = {f"G{k}S": sum(1 for s in SEEDS if s in arm[f"G{k}"] and s in arm[f"G{k}S"]) for k in KS}
    conv = {f"G{k}": conversion(arm[f"G{k}"], arm[f"G{k}S"]) for k in KS}
    per = {a: K1.per_arm(arm[a], L) for a in arm}
    mean = lambda xs: float(np.mean(xs)) if xs else None
    gum = {a: dict(roots_per_run=mean([v[5] for v in arm[a].values() if v[5]]),
                   sims_per_run=mean([v[6] for v in arm[a].values() if v[6]]))
           for a in list(NEW) + list(OLD) if arm.get(a)}
    return dict(dropped_seeds=dropped, drops=sorted(drops), evaluable=evaluable, primary=prim, secondary=sec,
                replay=dict(verdict="REPLAY_OK" if not any(rep.values()) else "REPLAY_BROKEN", failing=rep,
                            seeds_checked=checked),
                act4_conversion=conv, per_arm=per, gumbel=gum)


def main(units, units_1k, units_2k8k, ref_units, out):
    new, drops, seen = load_arms(units, NEW, ENV_NEW)
    g1, d1, _ = load_arms(units_1k, {"G1": 1000}, ENV_OLD, skip=("B1",))
    g28, d28, _ = load_arms(units_2k8k, {a: OLD[a] for a in ("G2", "G4", "G8")}, ENV_OLD)
    old = {**g1, **g28}
    b1 = K1.load(units_1k)[0]
    W = module(HERE.parent / "gumbel_tuning_20261109" / "wholerun" / "analyze.py", "wr")
    ref, ref_bad = W.load(ref_units, "ref")[:2]
    res = analyze(new, drops, seen, old, b1, ref)
    res["drops_old"] = sorted(d1 + d28)
    res["ref_bad"] = [b for b in ref_bad if int(b.rsplit("-", 1)[1]) in SEEDS]
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"dropped seeds {len(res['dropped_seeds'])}, evaluable {res['evaluable']}, replay {res['replay']['verdict']} "
          f"{ {a: len(v) for a, v in res['replay']['failing'].items()} }")
    for k, c in res["primary"].items():
        if c.get("seeds"):
            print(f"  {k}: {c['heart_pp']['mean']:+.2f} pp 95% [{c['heart_pp']['ci95'][0]:+.2f}, {c['heart_pp']['ci95'][1]:+.2f}]"
                  f" 99% [{c['heart_pp_ci_bonferroni'][0]:+.2f}, {c['heart_pp_ci_bonferroni'][1]:+.2f}] -> {c['verdict']}"
                  f" (seeds {c['seeds']}, cpu x{c['cpu_ratio']:.2f})")
    for a, v in res["per_arm"].items():
        if v.get("games"):
            print(f"  {a}: Heart {100 * v['heart']:.2f}%  Act4 {100 * v['act4']:.2f}%  floor {v['floor']:.2f}  "
                  f"cpu/run {v['cpu_per_run']:.1f} s  games {v['games']}")
    for k, v in res["act4_conversion"].items():
        if v.get("seeds"):
            print(f"  per Act-4 arrival {k}: {v['old']:.1f}% -> {v['new']:.1f}% ({v['seeds']} seeds)")
    for k, v in res["secondary"].items():
        if v.get("seeds"):
            print(f"  {k}: {v['heart_pp']['mean']:+.2f} pp [{v['heart_pp']['ci95'][0]:+.2f}, {v['heart_pp']['ci95'][1]:+.2f}]"
                  f" cpu x{v['cpu_ratio']:.2f}")


def self_test():
    rng = np.random.default_rng(3)
    new, old, seen = {}, {}, set()
    ref = {}
    for s in SEEDS:
        for k, p4, conv_old, conv_new in ((1, 0.30, 0.75, 0.75), (2, 0.37, 0.73, 0.78), (4, 0.42, 0.71, 0.85),
                                          (8, 0.43, 0.74, 0.95)):
            reach = rng.random() < p4
            u = rng.random()
            floor = 56.0 if reach else float(rng.integers(5, 52))
            key = (f"[heart1_ppo] seed={s} decisions=90", f"roots k{k}", f"reuse k{k}")
            w_old, w_new = int(reach and u < conv_old), int(reach and u < conv_new)
            old[(f"G{k}", s)] = (w_old, int(reach), floor, 10.0 * k, 0, 400, 1000 * k * 400, key)
            new[(f"G{k}S", s)] = (w_new, int(reach), floor, 12.0 * k, 0, 400, 1000 * k * 400,
                                  key if not reach else key[:1] + ("roots x", "reuse x"))
            seen.add((f"G{k}S", s))
        ref[("G16", s)] = (int(rng.random() < 0.40), 1, 56.0, 500.0)
    r = analyze(new, [], seen, old, None, ref)
    assert r["replay"]["verdict"] == "REPLAY_OK", r["replay"]
    assert r["primary"]["G8S - G8"]["verdict"] == "G8S_BETTER", r["primary"]["G8S - G8"]
    assert r["primary"]["G1S - G1"]["verdict"] == "NO_DIFFERENCE_SHOWN", r["primary"]["G1S - G1"]
    assert r["primary"]["G8S - G8"]["heart_pp_ci_bonferroni"][0] < r["primary"]["G8S - G8"]["heart_pp"]["ci95"][0]
    assert r["act4_conversion"]["G8"]["seeds"] == sum(old[("G8", s)][1] for s in SEEDS)
    # A pre-Act-4 game that differs breaks the replay.
    s = next(x for x in SEEDS if old[("G2", x)][1] == 0)
    v = list(new[("G2S", s)])
    v[2] += 1
    new[("G2S", s)] = tuple(v)
    r = analyze(new, [], seen, old, None, ref)
    assert r["replay"]["verdict"] == "REPLAY_BROKEN" and r["replay"]["failing"]["G2S"] == [f"G2S-{s}"], r["replay"]
    r = analyze(new, [f"G4S-{x}" for x in range(111378400, 111378411)], seen, old, None, ref)
    assert all(c["verdict"] == "NOT_EVALUABLE" for c in r["primary"].values())
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 6:
        main(*sys.argv[1:])
    else:
        sys.exit(__doc__)
