#!/usr/bin/env python3
"""#418 live A/B: production CTM stack vs the pathb-r2 research candidate inside live OOC MCTS.

Pre-registered protocol: LIVE-AB-PREREG.md (written before any cohort seed ran). The
constants below are part of the pre-registration; do not edit them after the cohort starts.
Reads bestbench outputs only; runs no seeds. stdlib + numpy.

Run directory layout (one file set per unit = arm x block of seeds):
  <arm>-<lo>.csv  .csv.meta.json  .log  .trace.jsonl  [.mcts.csv  .mcts.csv.support.jsonl]
  arms: prod (OOC MCTS + production CTM), cand (OOC MCTS + candidate CTM), off (MCTS off, flat 10k)

usage:
  live_ab_analyze.py check   RUN_DIR --seed-lo N --seed-count N --git-sha SHA [--block 8]
  live_ab_analyze.py analyze RUN_DIR --seed-lo N --seed-count N --git-sha SHA [--block 8] --out REPORT.json
  live_ab_analyze.py selftest
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

SCHEMA = "ctm_live_ab_v1"
# ---- pre-registered constants (LIVE-AB-PREREG.md section 5) ----
REPS, RNG_SEED = 10000, 418063   # paired seed bootstrap, percentile 95% CI
ALPHA = 0.05                     # exact two-sided McNemar on discordant pairs
NONINF_MARGIN = -0.10            # NO_DIFFERENCE_DETECTED sub-flag: CI lower bound above -10 pp
MAX_DROPPED_PAIRS = 6            # more dropped primary pairs (stall/missing) -> verdict _PROVISIONAL
CANDIDATE_ID = "pathb-r2"
PROD_FAST = "selfplay/models/combat_transition_deepsets_lizard_t2.native"
PROD_STD = "selfplay/models/combat_transition_near_full_except_smoke_v2.native"
BOSS_FLOORS = {16, 33, 50}       # A0 act 1-3 boss floors (cross-check of the trace)
STALL_RX = re.compile(r"stall|depth bound")
# -----------------------------------------------------------------
ARMS = ("prod", "cand", "off")
MCTS_ARMS = ("prod", "cand")
CSV_HEADER = ["seed", "won", "floor", "act", "hpEnd", "maxHp", "fightsLost", "deathCombat", "deathEncounter", "sec"]
FAIL_RX = re.compile(r"^\[bestbench-seed-failure\] seed=(\d+) error=(.*)$")
MCTS_SUM = ("oocDecisions", "mctsOwned", "mctsFallback", "unsupportedCombats", "mctsSupportAborts",
            "imaginedCombats", "transitionSamples", "simulations", "hybridFallbackPreparations",
            "hybridFastSupportFailures", "hybridFallbackSupportFailures", "continuationLimitAborts")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ loading
def unit_los(seed_lo: int, seed_count: int, block: int) -> list[int]:
    return list(range(seed_lo, seed_lo + seed_count, block))


def load_unit(run: Path, arm: str, lo: int, n: int, git_sha: str, errors: list) -> dict:
    """One unit's rows, failures, traces, and integrity errors (appended to errors)."""
    base = run / f"{arm}-{lo}"
    tag = f"{arm}-{lo}"
    out = {"rows": {}, "failures": {}, "battles": {}, "mcts": {}, "support": {}, "present": False}
    csv_path = Path(str(base) + ".csv")
    if not csv_path.exists():
        errors.append(f"{tag}: missing results CSV")
        return out
    out["present"] = True
    expected = set(range(lo, lo + n))
    with csv_path.open(newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames != CSV_HEADER:
            errors.append(f"{tag}: CSV header {r.fieldnames}")
            return out
        for x in r:
            s = int(x["seed"])
            if s not in expected:
                errors.append(f"{tag}: seed {s} outside unit")
            if s in out["rows"]:
                errors.append(f"{tag}: duplicate seed {s}")
            out["rows"][s] = {"won": int(x["won"]), "floor": int(x["floor"]), "act": int(x["act"]),
                              "hpEnd": int(x["hpEnd"]), "maxHp": int(x["maxHp"]),
                              "fightsLost": int(x["fightsLost"]), "deathEncounter": int(x["deathEncounter"]),
                              "sec": float(x["sec"])}
    # sidecar: exactly one invocation record with the frozen configuration
    meta_path = Path(str(base) + ".csv.meta.json")
    metas = [json.loads(l) for l in meta_path.open()] if meta_path.exists() else []
    if len(metas) != 1:
        errors.append(f"{tag}: expected 1 sidecar record, found {len(metas)}")
    else:
        m, c = metas[0], metas[0].get("config", {})
        checks = {"seedBlock": m.get("seedBlock") == {"lo": lo, "hi": lo + n - 1}, "sims": m.get("sims") == 10000,
                  "asc": m.get("asc") == 0, "threads": m.get("threads") == 1, "fair": c.get("fairPlay") is True,
                  "backend": c.get("effectiveCombatBackend") == "native_silver",
                  "reuseCap": c.get("silverReuseCap") == 32768, "exactRoot": c.get("silverExactRootBudgets") is True,
                  "noLearnedStop": c.get("silverLearnedStopModel", "") == "",
                  "noAdaptive": c.get("silverAdaptiveEnabled") is False, "keysOff": c.get("collectKeys") is False,
                  "gitSha": c.get("executableGitSha") == git_sha, "noRootPrior": c.get("silverRootPrior", "") == ""}
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            errors.append(f"{tag}: sidecar mismatch {bad}")
    # log: failures and arm identity
    log_path = Path(str(base) + ".log")
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    if not text:
        errors.append(f"{tag}: missing or empty log")
    for line in text.splitlines():
        mm = FAIL_RX.match(line)
        if mm:
            out["failures"][int(mm.group(1))] = mm.group(2)
    banner = [l for l in text.splitlines() if l.startswith("[live OOC MCTS ON ")]
    cand_line = f"[ctm-research-candidate] candidate_id={CANDIDATE_ID}" in text
    if arm == "off":
        if banner or "[ctm-research-candidate]" in text:
            errors.append(f"{tag}: MCTS or candidate active in the off arm")
    else:
        if len(banner) != 1:
            errors.append(f"{tag}: expected one live OOC MCTS banner, found {len(banner)}")
        else:
            b = banner[0]
            need = ["sims=2048", "active_lizard_correction=1", "leaf_value=screengbm", "cpuct=1.5",
                    "root_selection=visits", "early_stop=1", "merge_outcomes=0", "dispatch=precombat_entropic_brew"]
            if arm == "prod":
                need += [f"combat_model={PROD_FAST}", f"brew_fallback_model={PROD_STD}"]
            else:
                need += ["FAST-final.native", "STD1-escape.native"]
                if PROD_FAST in b or PROD_STD in b:
                    errors.append(f"{tag}: candidate arm loaded a production artifact path")
            miss = [k for k in need if k not in b]
            if miss:
                errors.append(f"{tag}: banner lacks {miss}")
        if (arm == "cand") != cand_line or (arm == "prod" and "[ctm-research-candidate]" in text):
            errors.append(f"{tag}: research-candidate log line {'missing' if arm == 'cand' else 'present'}")
    # decision trace: battle rows per seed
    tr = Path(str(base) + ".trace.jsonl")
    if not tr.exists():
        errors.append(f"{tag}: missing decision trace")
    else:
        for line in tr.open():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "battle":
                out["battles"].setdefault(int(row["seed"]), []).append(row)
    # MCTS per-seed trace (MCTS arms only)
    if arm in MCTS_ARMS:
        mp = Path(str(base) + ".mcts.csv")
        if not mp.exists():
            errors.append(f"{tag}: missing MCTS trace")
        else:
            with mp.open(newline="") as f:
                for x in csv.DictReader(f):
                    out["mcts"][int(x["seed"])] = {k: float(x[k]) for k in x if k != "seed"}
        sp = Path(str(mp) + ".support.jsonl")
        if sp.exists():
            for line in sp.open():
                if line.strip():
                    row = json.loads(line)
                    out["support"][int(row["seed"])] = row.get("reasons", {})
    return out


def load_arm(run: Path, arm: str, a) -> dict:
    errors: list[str] = []
    arm_d = {"rows": {}, "failures": {}, "battles": {}, "mcts": {}, "support": {}, "errors": errors}
    for lo in unit_los(a.seed_lo, a.seed_count, a.block):
        n = min(a.block, a.seed_lo + a.seed_count - lo)
        u = load_unit(run, arm, lo, n, a.git_sha, errors)
        for k in ("rows", "failures", "battles", "mcts", "support"):
            arm_d[k].update(u[k])
    for s in arm_d["rows"]:
        if s in arm_d["failures"]:
            errors.append(f"{arm}: seed {s} has both a row and a failure line")
    return arm_d


# ------------------------------------------------------------------ statistics
def boot_ci(x: np.ndarray, reps: int = REPS, seed: int = RNG_SEED) -> list[float] | None:
    """Mean and percentile 95% CI of a paired per-seed difference; fresh generator per statistic."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return None
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(reps, len(x)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [float(x.mean()), float(lo), float(hi)]


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar (binomial on discordant pairs, p = 1/2)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return float(min(1.0, 2 * tail))


# ------------------------------------------------------------------ per-run features
def run_features(battles: list[dict], row: dict) -> dict:
    bs = sorted(battles, key=lambda r: r["fight"])
    boss = [b for b in bs if b["pre"]["room"] == "BOSS"]
    died = [b for b in bs if not b["won"]]
    smoke_fights = [b for b in bs if "SMOKE_BOMB" in b["pre"]["potions"]]
    escapes = [b for b in smoke_fights if b["won"] and b["pre"]["room"] != "BOSS"
               and b["post"]["potions"].count("SMOKE_BOMB") < b["pre"]["potions"].count("SMOKE_BOMB")]
    boss_hp = {}
    for b in boss:
        boss_hp.setdefault(int(b["pre"]["act"]), (b["pre"]["hp"], b["pre"]["maxHp"]))
    return {
        "fights": len(bs),
        "boss_death": int(bool(died) and died[0]["pre"]["room"] == "BOSS"),
        "boss_death_act": int(died[0]["pre"]["act"]) if died and died[0]["pre"]["room"] == "BOSS" else 0,
        "boss_death_csv": int(row["won"] == 0 and row["floor"] in BOSS_FLOORS),
        "death_room": died[0]["pre"]["room"] if died else "",
        "bosses_entered": len(boss),
        "boss_hp": boss_hp,
        "mean_start_hp": float(np.mean([b["pre"]["hp"] for b in bs])) if bs else float("nan"),
        "mean_start_hp_frac": float(np.mean([b["pre"]["hp"] / b["pre"]["maxHp"] for b in bs])) if bs else float("nan"),
        "smoke_fights": len(smoke_fights),
        "smoke_fights_nonboss": sum(b["pre"]["room"] != "BOSS" for b in smoke_fights),
        "smoke_runs": int(bool(smoke_fights)),
        "escapes": len(escapes),
        "trace_won_last": int(bs[-1]["won"]) if bs else -1,
    }


def summarize(x) -> float:
    return float(np.mean(x)) if len(x) else float("nan")


# ------------------------------------------------------------------ report
def build_report(a) -> dict:
    run = Path(a.run_dir)
    data = {arm: load_arm(run, arm, a) for arm in ARMS}
    expected = set(range(a.seed_lo, a.seed_lo + a.seed_count))
    errors = [e for arm in ARMS for e in data[arm]["errors"]]
    census, dropped = {}, {}
    for arm in ARMS:
        d = data[arm]
        stalls = {s: m for s, m in d["failures"].items() if STALL_RX.search(m)}
        other = {s: m for s, m in d["failures"].items() if not STALL_RX.search(m)}
        missing = sorted(expected - set(d["rows"]) - set(d["failures"]))
        census[arm] = {"rows": len(d["rows"]), "stalls": {str(s): m for s, m in sorted(stalls.items())},
                       "otherFailures": {str(s): m for s, m in sorted(other.items())}, "missing": missing}
        if other:
            errors.append(f"{arm}: {len(other)} non-stall seed failures (see census)")
        dropped[arm] = set(d["failures"]) | set(missing)
        # trace / CSV consistency on completed seeds
        for s, row in d["rows"].items():
            bl = d["battles"].get(s, [])
            if not bl:
                errors.append(f"{arm}: seed {s} has no battle trace rows")
            elif row["won"] == 1 and any(not b["won"] for b in bl):
                errors.append(f"{arm}: seed {s} won but the trace has a lost fight")
            if arm in MCTS_ARMS and s not in d["mcts"]:
                errors.append(f"{arm}: seed {s} has no MCTS trace row")
    feats = {arm: {s: run_features(data[arm]["battles"].get(s, []), r) for s, r in data[arm]["rows"].items()}
             for arm in ARMS}

    def pairs(x, y):
        return sorted((set(data[x]["rows"]) & set(data[y]["rows"])) - dropped[x] - dropped[y])

    def compare(x, y, primary=False) -> dict:
        ps = pairs(x, y)
        wx = np.array([data[x]["rows"][s]["won"] for s in ps])
        wy = np.array([data[y]["rows"][s]["won"] for s in ps])
        fx = np.array([data[x]["rows"][s]["floor"] for s in ps])
        fy = np.array([data[y]["rows"][s]["floor"] for s in ps])
        b, c = int(((wx == 1) & (wy == 0)).sum()), int(((wx == 0) & (wy == 1)).sum())
        bdx = np.array([feats[x][s]["boss_death"] for s in ps])
        bdy = np.array([feats[y][s]["boss_death"] for s in ps])
        out = {"pairs": len(ps), "winRate": [summarize(wx), summarize(wy)],
               "win": boot_ci(wx - wy), "discordant": [b, c], "mcnemarP": mcnemar_exact(b, c),
               "floor": boot_ci(fx - fy), "score_floor_plus_10won": boot_ci((fx + 10 * wx) - (fy + 10 * wy)),
               "bossDeaths": [int(bdx.sum()), int(bdy.sum())], "bossDeath": boot_ci(bdx - bdy),
               "secRatio": summarize([data[x]["rows"][s]["sec"] for s in ps]) /
                           max(summarize([data[y]["rows"][s]["sec"] for s in ps]), 1e-9)}
        if primary:
            out["droppedPairs"] = sorted((expected - set(ps)))
        return out

    primary = compare("cand", "prod", primary=True)
    lo, hi = primary["win"][1], primary["win"][2]
    p = primary["mcnemarP"]
    if errors:
        verdict = "INVALID"
    elif lo > 0 and p < ALPHA:
        verdict = "CANDIDATE_BETTER"
    elif hi < 0 and p < ALPHA:
        verdict = "CANDIDATE_WORSE"
    else:
        verdict = "NO_DIFFERENCE_DETECTED"
    flags = []
    if verdict == "NO_DIFFERENCE_DETECTED" and lo > NONINF_MARGIN:
        flags.append("NONINFERIOR_AT_10PP")
    if primary["bossDeath"] and primary["bossDeath"][1] > 0:
        flags.append("BOSS_DEATH_EXCESS")
    if verdict != "INVALID" and len(primary["droppedPairs"]) > MAX_DROPPED_PAIRS:
        verdict += "_PROVISIONAL"

    # secondaries (descriptive)
    ps = pairs("cand", "prod")
    sec = {"perArm": {}, "bossEntryHp": {}, "bossDeathCrossCheck": {}}
    for arm in ARMS:
        rows, f = data[arm]["rows"], feats[arm]
        s_arm = [s for s in rows if s not in dropped[arm]]
        bosses = {act: sum(act in f[s]["boss_hp"] for s in s_arm) for act in (1, 2, 3)}
        boss_deaths_act = {act: sum(f[s]["boss_death_act"] == act for s in s_arm) for act in (1, 2, 3)}
        per = {"runs": len(s_arm), "winRate": summarize([rows[s]["won"] for s in s_arm]),
               "meanFloor": summarize([rows[s]["floor"] for s in s_arm]),
               "cpuSecPerRun": summarize([rows[s]["sec"] for s in s_arm]),
               "meanHpAfterWin": summarize([rows[s]["hpEnd"] for s in s_arm if rows[s]["won"]]),
               "deaths": sum(1 - rows[s]["won"] for s in s_arm),
               "bossDeaths": sum(f[s]["boss_death"] for s in s_arm),
               "bossesEnteredByAct": {str(k): v for k, v in bosses.items()},
               "bossDeathsByAct": {str(k): v for k, v in boss_deaths_act.items()},
               "meanStartHp": summarize([f[s]["mean_start_hp"] for s in s_arm if f[s]["fights"]]),
               "meanStartHpFraction": summarize([f[s]["mean_start_hp_frac"] for s in s_arm if f[s]["fights"]]),
               "smokeHeldFights": sum(f[s]["smoke_fights"] for s in s_arm),
               "smokeHeldNonBossFights": sum(f[s]["smoke_fights_nonboss"] for s in s_arm),
               "runsWithSmokeHeldAtAFight": sum(f[s]["smoke_runs"] for s in s_arm),
               "escapes": sum(f[s]["escapes"] for s in s_arm)}
        if arm in MCTS_ARMS:
            m = data[arm]["mcts"]
            per["mcts"] = {k: float(sum(m[s].get(k, 0.0) for s in s_arm if s in m)) for k in MCTS_SUM}
            per["mcts"]["mctsCpuSecPerRun"] = summarize([m[s]["mctsCpuSec"] for s in s_arm if s in m])
            reasons: dict[str, float] = {}
            for s in s_arm:
                for k, v in data[arm]["support"].get(s, {}).items():
                    reasons[k] = reasons.get(k, 0) + v
            per["mcts"]["supportReasons"] = dict(sorted(reasons.items()))
        sec["perArm"][arm] = per
        sec["bossDeathCrossCheck"][arm] = sum(f[s]["boss_death"] != f[s]["boss_death_csv"] for s in s_arm)
    for act in (1, 2, 3):
        both = [s for s in ps if act in feats["cand"][s]["boss_hp"] and act in feats["prod"][s]["boss_hp"]]
        sec["bossEntryHp"][str(act)] = {
            "pairs": len(both),
            "hp": boot_ci([feats["cand"][s]["boss_hp"][act][0] - feats["prod"][s]["boss_hp"][act][0] for s in both]),
            "means": [summarize([feats[a_][s]["boss_hp"][act][0] for s in both]) for a_ in ("cand", "prod")]}
    sec["meanStartHp"] = boot_ci([feats["cand"][s]["mean_start_hp"] - feats["prod"][s]["mean_start_hp"] for s in ps])
    sec["escapesPerRun"] = boot_ci([feats["cand"][s]["escapes"] - feats["prod"][s]["escapes"] for s in ps])
    sec["smokeHeldFightsPerRun"] = boot_ci([feats["cand"][s]["smoke_fights"] - feats["prod"][s]["smoke_fights"] for s in ps])

    script = Path(__file__).resolve()
    return {"schema": SCHEMA, "runDir": str(run.resolve()), "seedLo": a.seed_lo, "seedCount": a.seed_count,
            "gitSha": a.git_sha, "scriptSha256": sha256(script), "numpy": np.__version__,
            "constants": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float, str))
                          and k not in ("SCHEMA",)},
            "verdict": verdict, "flags": flags, "integrityErrors": errors, "census": census,
            "primary_cand_minus_prod": primary,
            "descriptive": {"cand_minus_off": compare("cand", "off"), "prod_minus_off": compare("prod", "off")},
            "secondary": sec}


def cmd_check(a) -> int:
    run = Path(a.run_dir)
    errors = []
    for arm in ARMS:
        d = load_arm(run, arm, a)
        errors += d["errors"]
        print(json.dumps({"arm": arm, "rows": len(d["rows"]), "failures": d["failures"],
                          "secPerRun": summarize([r["sec"] for r in d["rows"].values()]),
                          "battleRows": sum(len(v) for v in d["battles"].values()),
                          "mctsRows": len(d["mcts"])}))
    print(json.dumps({"integrityErrors": errors}, indent=1))
    return 1 if errors else 0


# ------------------------------------------------------------------ self-test (synthetic data)
def _write_unit(run: Path, arm: str, lo: int, n: int, git_sha: str, outcome, fail=None) -> None:
    base = run / f"{arm}-{lo}"
    with open(str(base) + ".csv", "w") as f:
        f.write(",".join(CSV_HEADER) + "\n")
    meta = {"objective": "bestbench", "seedBlock": {"lo": lo, "hi": lo + n - 1}, "nSeeds": n, "asc": 0,
            "sims": 10000, "threads": 1,
            "config": {"fairPlay": True, "effectiveCombatBackend": "native_silver", "silverReuseCap": 32768,
                       "silverExactRootBudgets": True, "silverLearnedStopModel": "", "silverAdaptiveEnabled": False,
                       "collectKeys": False, "executableGitSha": git_sha}}
    Path(str(base) + ".csv.meta.json").write_text(json.dumps(meta) + "\n")
    log = ["[collect keys OFF]"]
    if arm == "cand":
        log.append(f"[ctm-research-candidate] candidate_id={CANDIDATE_ID}")
    if arm != "off":
        fast = PROD_FAST if arm == "prod" else "/x/cand/FAST-final.native"
        std = PROD_STD if arm == "prod" else "/x/cand/STD1-escape.native"
        log.append(f"[live OOC MCTS ON sims=2048 combat_model={fast} brew_fallback_model={std} "
                   "dispatch=precombat_entropic_brew active_lizard_correction=1 prior=policy temperature=1 "
                   "cpuct=1.5 widen_k=2 widen_alpha=0.5 max_depth=32 root_selection=visits early_stop=1 "
                   "gap_stop_20=0 merge_outcomes=0 leaf_value=screengbm leaf_combats=0 leaf_policy=v4]")
    trace, mcts = [], []
    rows = []
    for s in range(lo, lo + n):
        if fail and s in fail:
            log.append(f"[bestbench-seed-failure] seed={s} error={fail[s]}")
            continue
        won, death_floor, smoke = outcome(arm, s)
        floors = [3, 6, 10, 16, 20, 25, 33, 40, 45, 50]
        hp = 70
        last = len(floors) if won else floors.index(death_floor) + 1
        for i, fl in enumerate(floors[:last]):
            room = "BOSS" if fl in BOSS_FLOORS else "MONSTER"
            pots = ["SMOKE_BOMB"] if smoke and i == 1 else []
            lost = (not won) and i == last - 1
            post = [] if (pots and room != "BOSS") else pots
            trace.append({"seed": s, "kind": "battle", "fight": i + 1, "encounter": "X", "won": not lost,
                          "pre": {"act": 1 + (fl > 16) + (fl > 33), "floor": fl, "room": room, "hp": hp,
                                  "maxHp": 80, "potions": pots},
                          "post": {"act": 1, "floor": fl, "room": room, "hp": hp - 5, "maxHp": 80, "potions": post}})
            hp -= 3 if arm == "cand" else 4
        trace.append({"seed": s, "kind": "ooc", "idx": 0})
        rows.append([s, int(won), 50 if won else death_floor, 3, 30 if won else 0, 80, 0 if won else 1,
                     -1 if won else last, -1, 100.0 + (s % 7)])
        mcts.append(s)
    with open(str(base) + ".csv", "a") as f:
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")
    Path(str(base) + ".log").write_text("\n".join(log) + "\nBEST win%=50\n")
    with open(str(base) + ".trace.jsonl", "w") as f:
        for t in trace:
            f.write(json.dumps(t) + "\n")
    if arm != "off":
        hdr = ["seed"] + [k for k in MCTS_SUM] + ["mctsCpuSec"]
        with open(str(base) + ".mcts.csv", "w") as f:
            f.write(",".join(hdr) + "\n")
            for s in mcts:
                f.write(",".join([str(s)] + ["1"] * len(MCTS_SUM) + ["50.0"]) + "\n")
        with open(str(base) + ".mcts.csv.support.jsonl", "w") as f:
            for s in mcts:
                f.write(json.dumps({"seed": s, "reasons": {"hp_envelope": 1} if arm == "prod" else {}}) + "\n")


def _synth(run: Path, lo: int, count: int, block: int, sha: str, p_prod: float, p_cand: float, rng_seed: int,
           fail=None) -> None:
    rng = np.random.default_rng(rng_seed)
    u = {s: rng.random() for s in range(lo, lo + count)}           # shared latent seed difficulty -> pairing
    noise = {(a_, s): rng.random() for a_ in ARMS for s in range(lo, lo + count)}

    def outcome(arm, s):
        p = {"prod": p_prod, "cand": p_cand, "off": 0.78}[arm]
        won = (0.6 * u[s] + 0.4 * noise[(arm, s)]) < p
        return won, (16 if s % 3 == 0 else 33 if s % 3 == 1 else 45), s % 5 == 0

    for blo in range(lo, lo + count, block):
        for arm in ARMS:
            _write_unit(run, arm, blo, min(block, lo + count - blo), sha,
                        outcome, (fail or {}).get(arm))


def selftest() -> int:
    sha = "a" * 40
    ns = argparse.Namespace
    results = {}
    with tempfile.TemporaryDirectory() as td:
        for name, pp, pc, fail in [
                ("equal", 0.56, 0.56, None),
                ("better", 0.45, 0.80, None),
                ("worse", 0.80, 0.45, None),
                ("stall", 0.56, 0.56, {"cand": {63000003: "native Silver backend: stall: exceeded 1000 decisions"}}),
                ("other", 0.56, 0.56, {"prod": {63000004: "combat runtime research candidate identity"}})]:
            run = Path(td) / name
            run.mkdir()
            _synth(run, 63000000, 128, 8, sha, pp, pc, 7, fail)
            a = ns(run_dir=str(run), seed_lo=63000000, seed_count=128, block=8, git_sha=sha)
            rep = build_report(a)
            results[name] = rep
        assert results["equal"]["verdict"] == "NO_DIFFERENCE_DETECTED", results["equal"]["verdict"]
        assert results["better"]["verdict"] == "CANDIDATE_BETTER", results["better"]["primary_cand_minus_prod"]
        assert results["worse"]["verdict"] == "CANDIDATE_WORSE"
        assert results["stall"]["verdict"] == "NO_DIFFERENCE_DETECTED", results["stall"]["integrityErrors"]
        assert results["stall"]["primary_cand_minus_prod"]["pairs"] == 127
        assert results["stall"]["primary_cand_minus_prod"]["droppedPairs"] == [63000003]
        assert results["other"]["verdict"] == "INVALID"
        r = results["equal"]
        assert r["integrityErrors"] == [], r["integrityErrors"]
        pa = r["secondary"]["perArm"]
        assert pa["prod"]["escapes"] > 0 and pa["prod"]["escapes"] == pa["prod"]["smokeHeldNonBossFights"]
        assert r["secondary"]["bossDeathCrossCheck"] == {"prod": 0, "cand": 0, "off": 0}
        assert r["secondary"]["bossEntryHp"]["2"]["hp"][0] > 0     # cand loses less HP per fight in the synth
        # McNemar and bootstrap sanity
        assert abs(mcnemar_exact(10, 0) - 2 / 1024) < 1e-12 and mcnemar_exact(5, 5) == 1.0
        assert boot_ci(np.zeros(10)) == [0.0, 0.0, 0.0]
        # determinism: same inputs -> identical report
        a = ns(run_dir=str(Path(td) / "equal"), seed_lo=63000000, seed_count=128, block=8, git_sha=sha)
        assert json.dumps(build_report(a), sort_keys=True) == json.dumps(results["equal"], sort_keys=True)
        # integrity: a candidate log without the research-candidate line is INVALID
        logp = Path(td) / "equal" / "cand-63000000.log"
        logp.write_text(logp.read_text().replace("[ctm-research-candidate]", "[x]"))
        assert build_report(a)["verdict"] == "INVALID"
        # wrong git SHA is INVALID
        b = ns(run_dir=str(Path(td) / "better"), seed_lo=63000000, seed_count=128, block=8, git_sha="b" * 40)
        assert build_report(b)["verdict"] == "INVALID"
    print(json.dumps({k: [v["verdict"], v["primary_cand_minus_prod"]["win"], v["primary_cand_minus_prod"]["discordant"],
                          round(v["primary_cand_minus_prod"]["mcnemarP"], 5)] for k, v in results.items()}, indent=1))
    print("selftest OK")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "analyze"):
        c = sub.add_parser(name)
        c.add_argument("run_dir")
        c.add_argument("--seed-lo", type=int, required=True)
        c.add_argument("--seed-count", type=int, required=True)
        c.add_argument("--git-sha", required=True)
        c.add_argument("--block", type=int, default=8)
        if name == "analyze":
            c.add_argument("--out", required=True, type=Path)
    sub.add_parser("selftest")
    a = p.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "check":
        return cmd_check(a)
    if a.out.exists():
        raise SystemExit(f"{a.out} exists")
    rep = build_report(a)
    a.out.open("x").write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    pr = rep["primary_cand_minus_prod"]
    print(json.dumps({"verdict": rep["verdict"], "flags": rep["flags"], "pairs": pr["pairs"],
                      "winRate_cand_prod": pr["winRate"], "win": pr["win"], "discordant": pr["discordant"],
                      "mcnemarP": pr["mcnemarP"], "bossDeaths_cand_prod": pr["bossDeaths"],
                      "integrityErrors": rep["integrityErrors"][:20]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
