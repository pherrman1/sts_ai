#!/usr/bin/env python3
"""Per-type Silver potion weights vs flat 11, paired whole A20 runs (follow-up to ledger §510).

usage: python3 tools/analyze_silver_potion_weights.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_silver_potion_weights.py selftest

RUN_DIRs hold one-seed A20 bestbench units ``ARM-SEED.{csv,done,env,log}`` of the arms ``base``, ``level`` and
``type`` (docs/experiments/evidence/silver_potion_weights_20261017/arm_env.sh). Cohort: A20 seeds 111152000 .. +N-1
(N from that directory's COHORT file).
Primary: floor-reached difference type - base. Secondary: level - base and type - level. Each with a paired seed
bootstrap 95% CI (10,000 resamples, RNG 510): BETTER when the lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN. Descriptive: act-3 clears (won), exact McNemar, end HP, boss deaths, seconds, pairs that differ.

Validity: a unit with rc != 0 is allowed only when its log names a ``[bestbench-seed-failure]``, it hit the 4 h
timeout (rc=124), or the worker recorded a stall (``stall-ARM-SEED.txt``); such seeds drop out of all pairs and are
counted. Every unit's ``.env`` must set STS_SILVER_POTION_WEIGHTS to its arm's value (unset for base) and must not
set STS_SILVER_ESCAPE_PENALTY. Any other gap, failure, wrong ``.env`` or non-cohort row labels the result INVALID.
"""
import glob, json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_rollout3_confirm import mcnemar, read_rows  # noqa: E402

REPS, RNG_SEED, SEED0 = 10000, 510, 111152000
ARMS = ("base", "level", "type")
CONTRASTS = (("type", "base"), ("level", "base"), ("type", "level"))
BOSS_FLOORS = {16, 33, 50, 51}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "silver_potion_weights_20261017")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
UNIT_RE = re.compile(r"(base|level|type)-(\d+)\.(csv|done)")


def expected_weights():
    return {"base": None, "level": "FAIRY_POTION=11,SMOKE_BOMB=11,*=7.8",
            "type": open(os.path.join(EVIDENCE, "WEIGHTS_TYPE")).read().strip()}


def env_ok(path, arm, expect):
    try:
        env = dict(l.rstrip("\n").split("=", 1) for l in open(path) if "=" in l)
    except OSError:
        return False
    return env.get("STS_SILVER_POTION_WEIGHTS") == expect[arm] and "STS_SILVER_ESCAPE_PENALTY" not in env


def cohort_from_file():
    return range(SEED0, SEED0 + int(open(os.path.join(EVIDENCE, "COHORT")).read().split()[0]))


def load(run_dirs, expect):
    rows = {a: {} for a in ARMS}
    done = {a: [] for a in ARMS}
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, "*"))):
            m = UNIT_RE.fullmatch(os.path.basename(path))
            if not m:
                continue
            arm = m.group(1)
            if m.group(3) == "csv":
                read_rows(path, rows[arm])
            else:
                log, line, seed = path[:-5] + ".log", open(path).read().strip(), int(m.group(2))
                fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
                stalled = os.path.exists(os.path.join(d, f"stall-{os.path.basename(path)[:-5]}.txt"))
                done[arm].append({"line": line, "seed": seed, "seed_failures": fails,
                                  "timeout": bool(re.search(r"\brc=124\b", line)), "stalled": stalled,
                                  "env_ok": env_ok(path[:-5] + ".env", arm, expect)})
    return rows, done


def analyze(rows, done, cohort):
    dropped = lambda d: d["timeout"] or d["stalled"]
    failed = {a: sorted({s for d in done[a] for s in d["seed_failures"]} | {d["seed"] for d in done[a] if dropped(d)})
              for a in ARMS}
    bad = [d["line"] for a in ARMS for d in done[a]
           if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"] and not dropped(d)]
    bad += [d["line"] + " (wrong .env)" for a in ARMS for d in done[a] if not d["env_ok"]]
    drop_seeds = set().union(*(set(failed[a]) for a in ARMS))
    missing = {a: sorted(set(cohort) - set(rows[a]) - set(failed[a])) for a in ARMS}
    extra = sorted(set().union(*(set(rows[a]) for a in ARMS)) - set(cohort))
    seeds = sorted(set(cohort).intersection(*(set(rows[a]) for a in ARMS)) - drop_seeds)
    out = {"cohort": [cohort.start, cohort.stop - 1], "dropped_seeds": failed,
           "timeouts": [d["line"] for a in ARMS for d in done[a] if d["timeout"]],
           "stalls": [d["line"] for a in ARMS for d in done[a] if d["stalled"]],
           "invalid_units": bad, "missing_cohort_seeds": missing, "non_cohort_seeds": extra, "pairs": len(seeds)}
    if bad or any(missing.values()) or extra or not seeds:
        out["label"] = "INVALID"
        return out
    rng = np.random.default_rng(RNG_SEED)
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))
    col = lambda a, k: np.array([float(rows[a][s][k]) for s in seeds])

    def ci(x):
        boot = x[idx].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]

    out.update({
        "wins": {a: int(col(a, "won").sum()) for a in ARMS},
        "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
        "boss_deaths": {a: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "reached_floor_50": {a: int((col(a, "floor") >= 50).sum()) for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
        "contrasts": {}, "label": {},
    })
    for x, y in CONTRASTS:
        wx, wy = col(x, "won"), col(y, "won")
        b, c = int(((wx == 1) & (wy == 0)).sum()), int(((wx == 0) & (wy == 1)).sum())
        df, dw = col(x, "floor") - col(y, "floor"), wx - wy
        key = f"{x}-{y}"
        out["contrasts"][key] = {
            "delta_floor": float(df.mean()), "delta_floor_ci95": ci(df),
            "delta_win": float(dw.mean()), "delta_win_ci95": ci(dw),
            "discordant_x_only": b, "discordant_y_only": c, "mcnemar_p": mcnemar(b, c),
            "delta_hp_end": float((col(x, "hpEnd") - col(y, "hpEnd")).mean()),
            "pairs_differing": int(sum(1 for s in seeds if any(rows[x][s][k] != rows[y][s][k]
                                                              for k in ("won", "floor", "hpEnd", "maxHp")))),
        }
        lo, hi = out["contrasts"][key]["delta_floor_ci95"]
        out["label"][key] = "BETTER" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN"
    return out


def selftest():
    import tempfile
    rng = np.random.default_rng(1)
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    expect = {"base": None, "level": "L", "type": "T"}
    cohort = range(100, 200)
    with tempfile.TemporaryDirectory() as t:
        wins = {s: (int(rng.random() < .9), int(rng.random() < .1)) for s in cohort}
        for arm in ARMS:
            for s in cohort:
                w = wins[s][0] if arm == "type" else wins[s][1]   # level plays exactly like base
                with open(os.path.join(t, f"{arm}-{s}.csv"), "w") as f:
                    f.write(hdr + f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
                open(os.path.join(t, f"{arm}-{s}.done"), "w").write(f"tag={arm}-{s} rc=0")
                open(os.path.join(t, f"{arm}-{s}.env"), "w").write(
                    "STS_X=1\n" + (f"STS_SILVER_POTION_WEIGHTS={expect[arm]}\n" if expect[arm] else ""))
        res = analyze(*load([t], expect), cohort)
        assert res["pairs"] == 100 and res["label"]["type-base"] == "BETTER" and res["label"]["level-base"] == "NOT_SHOWN", res
        assert res["label"]["type-level"] == "BETTER", res
        assert analyze(*load([t], expect), range(100, 201))["label"] == "INVALID"   # seed 200 missing
        assert analyze(*load([t], expect), range(101, 200))["label"] == "INVALID"   # seed 100 extra
        open(os.path.join(t, "base-107.done"), "w").write("tag=base-107 rc=124")    # timeout: seed dropped
        open(os.path.join(t, "stall-type-108.txt"), "w").write("bt")
        open(os.path.join(t, "type-108.done"), "w").write("tag=type-108 rc=143")    # stall kill: seed dropped
        res = analyze(*load([t], expect), cohort)
        assert res["pairs"] == 98 and res["label"] != "INVALID", res
        assert res["dropped_seeds"] == {"base": [107], "level": [], "type": [108]}, res
        open(os.path.join(t, "level-110.env"), "w").write("STS_SILVER_POTION_WEIGHTS=T\n")
        assert analyze(*load([t], expect), cohort)["label"] == "INVALID"            # wrong weights
        open(os.path.join(t, "level-110.env"), "w").write("STS_SILVER_POTION_WEIGHTS=L\nSTS_SILVER_ESCAPE_PENALTY=0,0\n")
        assert analyze(*load([t], expect), cohort)["label"] == "INVALID"            # escape penalty overridden
        open(os.path.join(t, "base-111.env"), "w").write("STS_SILVER_POTION_WEIGHTS=L\n")
        open(os.path.join(t, "level-110.env"), "w").write("STS_SILVER_POTION_WEIGHTS=L\n")
        assert analyze(*load([t], expect), cohort)["label"] == "INVALID"            # base with weights
        open(os.path.join(t, "base-111.env"), "w").write("STS_X=1\n")
        open(os.path.join(t, "base-105.done"), "w").write("tag=base-105 rc=1")
        assert analyze(*load([t], expect), cohort)["label"] == "INVALID"            # failed unit
    assert len(cohort_from_file()) <= 2000 and expected_weights()["type"].endswith("*=7.8")
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:], expected_weights()), cohort_from_file())
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("label", "pairs", "wins", "mean_floor")}))
