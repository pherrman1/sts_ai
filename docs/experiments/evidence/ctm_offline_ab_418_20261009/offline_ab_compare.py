#!/usr/bin/env python3
"""#418 offline A/B: production CTM stack vs the Path B research candidate on recorded rows.

Pre-registered protocol: OFFLINE-AB-RUNBOOK.md (written before any scoring). The decision
constants below are part of the pre-registration; do not edit them after scoring starts.
Reads rows and `one_combat ctmscorerows` CSVs only; runs no seeds. stdlib + numpy.

usage:
  offline_ab_compare.py extract --union U --out DIR
      TEST rows (split_for_seed) of every assembled scope named in U/row_scopes.json
      -> DIR/rows/<scope>.jsonl, DIR/tags/<scope>.csv, DIR/extract.json
  offline_ab_compare.py tag --rows ROWS.jsonl --scope NAME --out TAGS.csv
      tags for any other rows file (e.g. the Stage 0 learned arm)
  offline_ab_compare.py compare --prod P.csv --cand C.csv --label L --out R.json
      [--tags T.csv] [--split test|all] [--role gate|secondary|replication] [--reps 2000] [--seed 418]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

SCHEMA = "ctm_offline_ab_v1"
# ---- pre-registered constants (OFFLINE-AB-RUNBOOK.md "Decision rule") ----
EPS = 1e-6                      # p_death clip and HP log-prob floor (as Stage 0 analyze.py)
REPS, RNG_SEED = 2000, 418      # paired source-seed bootstrap
MARGIN_SURV_NLL = 0.005         # nat per fight, candidate minus production, 95% CI upper bound
MARGIN_HP_NLL = 0.03            # nat per won fight
BOSS_MARGIN_SURV_NLL = 0.02     # guard on boss fights
BOSS_MARGIN_HP_NLL = 0.10
CAND_BIAS_BAND = 0.01           # candidate survival bias 95% CI must lie inside +-band (gate slice)
MAX_PROD_ONLY_FRACTION = 0.001  # production-supported rows the candidate refuses
HP_ZERO_EXTRA_FRACTION = 1e-4   # extra zero-probability HP wins allowed, as a fraction of wins
SLICE_MIN_ROWS, SLICE_MIN_SEEDS = 200, 20
CAND_ONLY_MIN_ROWS, CAND_ONLY_BIAS_BAND = 100, 0.05
# ---------------------------------------------------------------------------

HEADER = ("source_seed,fight_idx,act,floor,room_class,encounter,teacher_id,run_valid,quarantine_reason,"
          "combat_outcome,pre_hp,pre_max_hp,post_hp,post_max_hp,scored,support_reason,p_death,"
          "win_hp_fraction,expected_win_hp,hist_mass,log_p_post_hp").split(",")
LABEL_FIELDS = HEADER[:14]
WIN, LOSS = 1, 2                # sts::Outcome (include/combat/BattleContext.h)
SMOKE_BOMB, ENTROPIC_BREW, FAIRY_POTION = 37, 17, 21   # sts::Potion ordinals (include/constants/Potions.h)
LIZARD_TAIL = 35                # sts::RelicId ordinal (include/constants/Relics.h)
TAG_FIELDS = ["source_seed", "fight_idx", "scope", "split", "run_valid", "has_transition", "boss",
              "smoke_held", "smoke_eligible", "escaped", "brew_held", "fairy_held", "lizard_active", "in_union"]
SEED_RX = re.compile(rb'"sourceSeed":\s*(\d+)')
FIGHT_RX = re.compile(rb'"fightIdx":\s*(\d+)')


def split_for_seed(seed: int) -> str:
    """combat_transition_model_experiment.split_for_seed (80/10/10 by source seed)."""
    b = int.from_bytes(hashlib.sha256(f"combat-transition-model-v1:{int(seed)}".encode()).digest()[:8], "big") % 100
    return "train" if b < 80 else "validation" if b < 90 else "test"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ tags / extract
def row_tags(row: dict, scope: str) -> dict:
    t = row["transition"]
    out = {"source_seed": int(row["sourceSeed"]), "fight_idx": int(row["fightIdx"]), "scope": scope,
           "split": split_for_seed(row["sourceSeed"]), "run_valid": int(bool(row["runValid"])),
           "has_transition": int(t is not None), "boss": int(row["roomClass"] == "BOSS"), "in_union": ""}
    for k in ("smoke_held", "smoke_eligible", "escaped", "brew_held", "fairy_held", "lizard_active"):
        out[k] = ""
    if t is not None:
        pre = t["pre"]
        usable = pre["potions"][:pre["potionCapacity"]]
        out["smoke_held"] = int(SMOKE_BOMB in usable)
        out["smoke_eligible"] = int(SMOKE_BOMB in usable and not out["boss"])
        out["escaped"] = int(bool(t["post"]["smokeBombUsed"]) and int(t["combatOutcome"]) == WIN)
        out["brew_held"] = int(ENTROPIC_BREW in pre["potions"])
        out["fairy_held"] = int(FAIRY_POTION in pre["potions"])
        out["lizard_active"] = int(any(r["id"] == LIZARD_TAIL and r["data"] == 1 for r in pre["relics"]))
    return out


def write_tags(path: Path, tags: list[dict]) -> None:
    with path.open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TAG_FIELDS)
        w.writeheader()
        w.writerows(tags)


def cmd_tag(rows: Path, scope: str, out: Path) -> None:
    tags = [row_tags(json.loads(line), scope) for line in rows.open(encoding="utf-8") if line.strip()]
    write_tags(out, tags)
    print(json.dumps({"rows": len(tags), "seeds": len({t["source_seed"] for t in tags}), "out": str(out)}))


def cmd_extract(union: Path, out: Path) -> None:
    scopes = json.loads((union / "row_scopes.json").read_text(encoding="utf-8"))
    (out / "rows").mkdir(parents=True)          # refuses an existing DIR/rows
    (out / "tags").mkdir()
    receipt = {"schema": SCHEMA + "_extract", "union": str(union.resolve()),
               "rowScopesSha256": sha256(union / "row_scopes.json"), "scopes": {}}
    # TEST keys the union kept, per scope row range.
    union_keys: dict[str, set] = {s: set() for s in scopes}
    ranges = sorted((r["firstRow"], r["firstRow"] + r["rows"], s) for s, r in scopes.items())
    with (union / "corpus.jsonl").open("rb") as f:
        for i, line in enumerate(f):
            seed = int(SEED_RX.search(line).group(1))
            if split_for_seed(seed) != "test":
                continue
            scope = next(s for lo, hi, s in ranges if lo <= i < hi)
            union_keys[scope].add((seed, int(FIGHT_RX.search(line).group(1))))
    for scope, r in sorted(scopes.items()):
        mpath = Path(r["manifest"])
        if sha256(mpath) != r["manifestSha256"]:
            raise SystemExit(f"{scope}: scope manifest {mpath} differs from row_scopes.json")
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        if manifest.get("forcedSetup") != scope:
            raise SystemExit(f"{scope}: manifest forcedSetup {manifest.get('forcedSetup')!r}")
        corpus = Path(manifest["csv"]["path"])
        if sha256(corpus) != manifest["csv"]["sha256"]:
            raise SystemExit(f"{scope}: {corpus} SHA256 differs from its manifest")
        rows_out, tags = out / "rows" / f"{scope}.jsonl", []
        with corpus.open("rb") as src, rows_out.open("xb") as sink:
            for line in src:
                if split_for_seed(int(SEED_RX.search(line).group(1))) != "test":
                    continue
                sink.write(line if line.endswith(b"\n") else line + b"\n")
                t = row_tags(json.loads(line), scope)
                t["in_union"] = int((t["source_seed"], t["fight_idx"]) in union_keys[scope])
                tags.append(t)
        write_tags(out / "tags" / f"{scope}.csv", tags)
        keys = [(t["source_seed"], t["fight_idx"]) for t in tags]
        if len(set(keys)) != len(keys):
            raise SystemExit(f"{scope}: duplicate (source_seed, fight_idx) keys")
        missing = union_keys[scope] - set(keys)
        if missing:
            raise SystemExit(f"{scope}: {len(missing)} union TEST rows are not in the scope corpus")
        receipt["scopes"][scope] = {
            "corpus": str(corpus), "corpusSha256": manifest["csv"]["sha256"], "testRows": len(tags),
            "testSeeds": len({k[0] for k in keys}), "inUnion": sum(t["in_union"] for t in tags),
            "smokeHeld": sum(t["smoke_held"] == 1 for t in tags), "escaped": sum(t["escaped"] == 1 for t in tags),
            "rowsSha256": sha256(rows_out), "tagsSha256": sha256(out / "tags" / f"{scope}.csv")}
    (out / "extract.json").open("x", encoding="utf-8").write(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=1, sort_keys=True))


# ------------------------------------------------------------------ compare
def read_scores(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames != HEADER:
            raise SystemExit(f"{path}: not a ctmscorerows CSV (header differs)")
        rows = {}
        for x in r:
            k = (int(x["source_seed"]), int(x["fight_idx"]))
            if k in rows:
                raise SystemExit(f"{path}: duplicate key {k}")
            rows[k] = x
    return rows


def stack_arrays(rows: list[dict]) -> dict:
    n = len(rows)
    scored = np.array([x["scored"] == "1" for x in rows])
    pd = np.full(n, np.nan); lp = np.full(n, np.nan); ehp = np.full(n, np.nan)
    for i, x in enumerate(rows):
        if scored[i]:
            pd[i] = float(x["p_death"]); ehp[i] = float(x["expected_win_hp"])
            if x["log_p_post_hp"] != "":
                lp[i] = float(x["log_p_post_hp"])   # "-inf" parses to -inf
    return {"scored": scored, "pd": pd, "lp": lp, "ehp": ehp,
            "reason": np.array([x["support_reason"] for x in rows])}


def per_row(s: dict, died: np.ndarray, post_hp: np.ndarray) -> dict:
    pd = np.clip(s["pd"], EPS, 1 - EPS)
    win = died == 0
    lp = s["lp"]
    return {
        "survival_nll": -(died * np.log(pd) + (1 - died) * np.log(1 - pd)),
        "brier": (pd - died) ** 2,
        "survival_bias": died - pd,               # predicted P(win) minus observed win; + = optimistic
        "hp_nll": np.where(win & ~np.isnan(lp), -np.maximum(lp, math.log(EPS)), np.nan),
        "hp_zero": np.where(win & ~np.isnan(lp), (lp == -np.inf).astype(float), np.nan),
        "hp_bias": np.where(win, s["ehp"] - post_hp, np.nan),   # predicted minus observed post HP
        "hp_mae": np.where(win, np.abs(s["ehp"] - post_hp), np.nan),
    }


class Boot:
    """Paired source-seed bootstrap: resample seeds, keep every row of a drawn seed."""

    def __init__(self, seed_of_row: np.ndarray, reps: int, rng_seed: int):
        self.uniq, self.idx = np.unique(seed_of_row, return_inverse=True)
        rng = np.random.default_rng(rng_seed)
        S = len(self.uniq)
        self.counts = np.stack([np.bincount(rng.integers(0, S, S), minlength=S) for _ in range(reps)]).astype(float)

    def stat(self, values: np.ndarray, mask: np.ndarray) -> dict | None:
        m = mask & np.isfinite(values)
        n = int(m.sum())
        if n == 0:
            return None
        S = len(self.uniq)
        sums = np.bincount(self.idx[m], weights=values[m], minlength=S)
        cnt = np.bincount(self.idx[m], minlength=S).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            reps = (self.counts @ sums) / (self.counts @ cnt)
        reps = reps[np.isfinite(reps)]
        if not len(reps):
            return None
        lo, hi = np.percentile(reps, [2.5, 97.5])
        return {"mean": float(values[m].mean()), "ci95": [float(lo), float(hi)], "n": n,
                "seeds": int(len(np.unique(self.idx[m]))), "reps": int(len(reps))}


def cmd_compare(a) -> dict:
    prod, cand = read_scores(a.prod), read_scores(a.cand)
    if set(prod) != set(cand):
        raise SystemExit("production and candidate CSVs do not cover the same rows")
    keys = sorted(prod)
    P, C = [prod[k] for k in keys], [cand[k] for k in keys]
    for p, c in zip(P, C):
        if any(p[f] != c[f] for f in LABEL_FIELDS):
            raise SystemExit(f"label fields differ for {(p['source_seed'], p['fight_idx'])}")
    seeds = np.array([k[0] for k in keys], dtype=np.int64)
    split = np.array([split_for_seed(s) for s in seeds])
    if a.split == "test" and (split != "test").any():
        raise SystemExit(f"{int((split != 'test').sum())} rows are not TEST seeds (use --split all only for out-of-sample sets)")
    tags = {}
    if a.tags:
        with a.tags.open(newline="", encoding="utf-8") as f:
            tags = {(int(t["source_seed"]), int(t["fight_idx"])): t for t in csv.DictReader(f)}
        if not set(keys) <= set(tags):
            raise SystemExit("tags do not cover every scored row")
    tag = lambda name: np.array([tags.get(k, {}).get(name, "") == "1" for k in keys])
    outcome = np.array([int(x["combat_outcome"]) if x["combat_outcome"] else 0 for x in P])
    valid = np.array([x["run_valid"] == "1" for x in P]) & np.isin(outcome, (WIN, LOSS))
    died = (outcome == LOSS).astype(float)
    post_hp = np.array([float(x["post_hp"]) if x["post_hp"] else np.nan for x in P])
    room = np.array([x["room_class"] for x in P]); act = np.array([int(x["act"]) for x in P])
    sp, sc = stack_arrays(P), stack_arrays(C)
    both = valid & sp["scored"] & sc["scored"]
    prod_only = valid & sp["scored"] & ~sc["scored"]
    cand_only = valid & ~sp["scored"] & sc["scored"]
    neither = valid & ~sp["scored"] & ~sc["scored"]
    mp, mc = per_row(sp, died, post_hp), per_row(sc, died, post_hp)
    boot = Boot(seeds, a.reps, a.seed)

    def reasons(mask, s):
        u, n = np.unique(s["reason"][mask], return_counts=True)
        return {str(k): int(v) for k, v in zip(u, n)}

    slices = {"all": np.ones(len(keys), bool)}
    for r in ("NORMAL", "ELITE", "BOSS"):
        slices[r.lower()] = room == r
    for x in sorted(set(act.tolist())):
        slices[f"act{x}"] = act == x
    for r in ("NORMAL", "ELITE", "BOSS"):
        for x in sorted(set(act.tolist())):
            slices[f"{r.lower()}_act{x}"] = (room == r) & (act == x)
    if tags:
        for name in ("escaped", "smoke_held", "lizard_active", "brew_held", "fairy_held"):
            slices[name] = tag(name)
        slices["not_in_union"] = ~tag("in_union") if any(t.get("in_union", "") != "" for t in tags.values()) else np.zeros(len(keys), bool)
    metrics = ("survival_nll", "brier", "survival_bias", "hp_nll", "hp_bias", "hp_mae", "hp_zero")

    def absolute(m, mask):
        return {k: boot.stat(m[k], mask) for k in metrics}

    def deltas(mask):
        return {k: boot.stat(mc[k] - mp[k], mask) for k in metrics}

    res = {"schema": SCHEMA, "label": a.label, "role": a.role, "split": a.split,
           "inputs": {"prod": str(a.prod), "prodSha256": sha256(a.prod), "cand": str(a.cand),
                      "candSha256": sha256(a.cand), "tags": str(a.tags) if a.tags else None,
                      "tagsSha256": sha256(a.tags) if a.tags else None,
                      "script": str(Path(__file__).resolve()), "scriptSha256": sha256(Path(__file__))},
           "numpy": np.__version__, "bootstrap": {"reps": a.reps, "rngSeed": a.seed, "unit": "source_seed"},
           "constants": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float))},
           "census": {"rows": len(keys), "seeds": int(len(np.unique(seeds))), "valid": int(valid.sum()),
                      "invalid": int((~valid).sum()), "wins": int((valid & (died == 0)).sum()),
                      "losses": int((valid & (died == 1)).sum()), "both": int(both.sum()),
                      "prodOnly": int(prod_only.sum()), "candOnly": int(cand_only.sum()), "neither": int(neither.sum()),
                      "prodSupported": int((valid & sp["scored"]).sum()), "candSupported": int((valid & sc["scored"]).sum()),
                      "prodOnlyCandReasons": reasons(prod_only, sc), "candOnlyProdReasons": reasons(cand_only, sp),
                      "neitherProdReasons": reasons(neither, sp), "neitherCandReasons": reasons(neither, sc),
                      "hpZeroBoth": {"prod": int(np.nansum(mp["hp_zero"][both])), "cand": int(np.nansum(mc["hp_zero"][both]))},
                      "hpZeroCandSupported": int(np.nansum(mc["hp_zero"][valid & sc["scored"]]))},
           "both": {}, "candOnly": {}, "prodOnly": {}}
    for name, m in slices.items():
        mask = both & m
        if mask.any():
            res["both"][name] = {"n": int(mask.sum()), "production": absolute(mp, mask),
                                 "candidate": absolute(mc, mask), "candidateMinusProduction": deltas(mask)}
        if (cand_only & m).any():
            res["candOnly"][name] = absolute(mc, cand_only & m)
        if (prod_only & m).any():
            res["prodOnly"][name] = absolute(mp, prod_only & m)
    res["flags"] = flags(res)
    if a.role == "gate":
        res["decision"] = decide(res)
    a.out.open("x", encoding="utf-8").write(json.dumps(res, indent=1, sort_keys=True) + "\n")
    summary = {"label": a.label, "census": {k: res["census"][k] for k in ("rows", "seeds", "valid", "both", "prodOnly", "candOnly")},
               "delta_all": {k: res["both"].get("all", {}).get("candidateMinusProduction", {}).get(k)
                             for k in ("survival_nll", "hp_nll", "brier", "hp_mae")},
               "flags": res["flags"], "decision": res.get("decision")}
    print(json.dumps(summary, indent=1))
    return res


def _d(res, sl, metric):
    return ((res["both"].get(sl) or {}).get("candidateMinusProduction") or {}).get(metric)


def flags(res) -> list[str]:
    out = []
    for sl, block in res["both"].items():
        d = block["candidateMinusProduction"]
        for metric in ("survival_nll", "hp_nll"):
            s = d.get(metric)
            if s and s["n"] >= SLICE_MIN_ROWS and s["seeds"] >= SLICE_MIN_SEEDS and s["ci95"][0] > 0:
                out.append(f"{'REPLICATION_CONFLICT' if res['role'] == 'replication' else 'SLICE_REGRESSION'}:{sl}:{metric}")
    co = (res["candOnly"].get("all") or {}).get("survival_bias")
    if co and co["n"] >= CAND_ONLY_MIN_ROWS and (co["ci95"][0] > CAND_ONLY_BIAS_BAND or co["ci95"][1] < -CAND_ONLY_BIAS_BAND):
        out.append("CANDIDATE_ONLY_MISCALIBRATED:all:survival_bias")
    z = res["census"]["hpZeroBoth"]
    if z["cand"] > z["prod"] + math.ceil(HP_ZERO_EXTRA_FRACTION * max(res["census"]["wins"], 1)):
        out.append("HP_ZERO_EXCESS")
    return out


def decide(res) -> dict:
    c = res["census"]
    ds, dh = _d(res, "all", "survival_nll"), _d(res, "all", "hp_nll")
    bs, bh = _d(res, "boss", "survival_nll"), _d(res, "boss", "hp_nll")
    bias = ((res["both"].get("all") or {}).get("candidate") or {}).get("survival_bias")
    if not (ds and dh and bs and bh and bias):
        return {"verdict": "FAIL", "reason": "a primary metric is missing"}
    guards = {
        "G1_support": c["prodOnly"] <= MAX_PROD_ONLY_FRACTION * c["prodSupported"],
        "G2_hp_zero": "HP_ZERO_EXCESS" not in res["flags"],
        "G3_boss": bs["ci95"][1] < BOSS_MARGIN_SURV_NLL and bh["ci95"][1] < BOSS_MARGIN_HP_NLL,
        "G4_calibration": -CAND_BIAS_BAND < bias["ci95"][0] and bias["ci95"][1] < CAND_BIAS_BAND,
    }
    within = ds["ci95"][1] < MARGIN_SURV_NLL and dh["ci95"][1] < MARGIN_HP_NLL
    better = ds["ci95"][1] < 0 or dh["ci95"][1] < 0
    worse = ds["ci95"][0] > 0 or dh["ci95"][0] > 0
    if not (all(guards.values()) and within):
        verdict = "FAIL"
    elif better and not worse:
        verdict = "PASS"
    else:
        verdict = "NON_INFERIOR"
    return {"verdict": verdict, "guards": guards, "nonInferior": within, "superiorOnOne": better,
            "worseOnOne": worse, "survivalNllDelta": ds, "hpNllDelta": dh}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("--union", required=True, type=Path); e.add_argument("--out", required=True, type=Path)
    t = sub.add_parser("tag"); t.add_argument("--rows", required=True, type=Path); t.add_argument("--scope", required=True)
    t.add_argument("--out", required=True, type=Path)
    c = sub.add_parser("compare")
    c.add_argument("--prod", required=True, type=Path); c.add_argument("--cand", required=True, type=Path)
    c.add_argument("--label", required=True); c.add_argument("--out", required=True, type=Path)
    c.add_argument("--tags", type=Path); c.add_argument("--split", choices=("test", "all"), default="test")
    c.add_argument("--role", choices=("gate", "secondary", "replication"), default="secondary")
    c.add_argument("--reps", type=int, default=REPS); c.add_argument("--seed", type=int, default=RNG_SEED)
    a = p.parse_args()
    if a.cmd == "extract":
        cmd_extract(a.union, a.out)
    elif a.cmd == "tag":
        cmd_tag(a.rows, a.scope, a.out)
    else:
        if a.role == "gate" and (a.reps != REPS or a.seed != RNG_SEED or a.split != "test"):
            raise SystemExit("the gate run uses the pre-registered reps, seed and TEST split")
        cmd_compare(a)


if __name__ == "__main__":
    sys.exit(main())
