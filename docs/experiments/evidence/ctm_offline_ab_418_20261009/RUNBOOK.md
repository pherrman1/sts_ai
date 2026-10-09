# #418 CTM retrain: pre-registered offline A/B (ctmscorerows, production vs pathb-r2 candidate)

Written 2026-10-09, before any candidate scoring, from a read-only pass over `7d62ba42` (origin/main). This step
continues CAPABILITIES-RUNBOOK.md and is the "ctmscorerows offline A/B" part of FULL-RETRAIN-PLAN.md item 10. It comes
before the independent review and the live 128-pair A/B. File:line citations refer to `7d62ba42`. The CTM C++
(`combat_transition_runtime.*`, `ctm_offline_score.cpp`, `one_combat.cpp`) and `selfplay/models` did not change between
`648334e3` (the `$OC` build) and `7d62ba42` (`git diff --stat`, empty).

**Seed guard.** No step here drives game seeds. `ctmscorerows` parses recorded `combat_transition_row_v2` rows and
writes one CSV line per row (ctm_offline_score.cpp:56-121; header comment at :1-2, "Reads rows only; runs no seeds"). The
seed guard therefore does not apply. Do not add any `combattransitiongen`/`combattransitionforcedgen` run to this step.

**What is compared.** Two complete CTM stacks score the same rows with the same `one_combat` binary:
* **production**: `one_combat ctmscorerows ROWS OUT` with no model arguments. That is the DeepSets Lizard T2 fast
  artifact, the Attention V2 Brew fallback and the active-Lizard correction (defaults in driver_shared.h:410-413, pinned
  SHA256s at combat_transition_runtime.cpp:166,446). The research-candidate environment variables must be **unset**.
* **candidate**: `one_combat ctmscorerows ROWS OUT $FASTF $STD1E 1` with the v3 manifest's two environment variables
  set. The candidate is `pathb-r2` with the **escape** capability on both children. Writhing Mass + Ritual Dagger stays
  excluded as in production. The Lizard r is the refitted fast r; there is no `lizardBrew` or `lizardFairy`, so Fairy and
  Brew active-Tail rows keep production's boundary behaviour.

The candidate path needs nothing beyond what C5 of CAPABILITIES-RUNBOOK already checked:
* The loader reads `STS_CTM_RESEARCH_CANDIDATE_MANIFEST` and `_SHA256` and requires both (runtime.cpp:252-258).
* It requires the manifest SHA256 to match (:258), `researchCandidate` = the manifest's `candidateId` (:356-358), and the
  file bytes to be the manifest's bytes for the role (:361-363). It also requires the header `capabilities` to equal the
  manifest's capabilities for the role (:367-369).
* `EntropicBrewFallbackCombatTransitionSampler` adds three pair checks:
  * the standard file SHA256 = `standard.artifactSha256` (:942-944);
  * the standard header's `supportExclusions` = the list its capabilities imply. For escape only that is
    `[pre_smoke_bomb_used, writhing_ritual_intersection]` (:678-683, :954);
  * the standard header's `qualification.classification` = `FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS` (:955), and fast and
    standard agree on escape and writhingRitual (:958-961).
* Active Lizard needs `activeLizardCorrection` in the fast header (:962-963).
* `ctmscorerows` itself has no capability check. Only `ctmescapefeatures` refuses an escape-capable artifact
  (ctm_offline_score.cpp:130), and this step does not use it.

With escape, `expectationState` mixes the escape-bit-0 and escape-bit-1 HP heads by the escape head for eligible states
(not a boss, Smoke Bomb in a usable slot; runtime.cpp:750-788). So `log_p_post_hp` of an escaped row is scored under
the mixture.

## 1. Inputs and hashes (verify all before scoring)

| Name | Path on Philipp's machine | SHA256 |
|---|---|---|
| `$OC` | `$WT/build/linux-gcc-release/one_combat`, built at `648334e38dc5c92bc57a9b531f2f9f3308a732ff` | record it (`sha256sum $OC`) |
| `$FASTF` (fast, DeepSets) | `$R2/durable/FAST-final.native` | `90806c25d784f7100b35ec755ad93756bf34d5aa297591891d5d3bb4314ba4f3` |
| `$STD1E` (standard, Attention) | `$R2/durable/STD1-escape.native` | `b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf` |
| `$M_FINAL` (v3 manifest) | `$R2/durable/candidate-v3.json` or `$R2/candidate-v3.json` (same bytes) | `d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d` |
| production fast | `$WT/selfplay/models/combat_transition_deepsets_lizard_t2.native` | `abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab` |
| production standard | `$WT/selfplay/models/combat_transition_near_full_except_smoke_v2.native` | `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd` |
| `$U` (Path B union the candidate trained on) | `$R2/union` (**assumed**; NEAR-FULL-RUNBOOK used `$R/union`) | `$U/corpus.jsonl` = its manifest's `csv.sha256` (checked below) |
| scope corpora | listed in `$U/row_scopes.json` (`manifest` + `manifestSha256` per scope) | checked by `extract` |
| `offline_ab_compare.py` | `$AB/offline_ab_compare.py` (pasted from section 3) | `ff71cf537a95729018053e50bffd9e95903b1697a1a12f358565fe76b7d70005` |

The manifest lists artifacts by SHA256, not by path. Copies under `durable/` therefore load the same as the originals.

## 2. Environment (applies to every step)

```sh
WT=/abs/path/wt-ctm-retrain                # run every command from here (production model paths are relative)
cd "$WT"
R2=$WT/build/ctm-retrain-a69f8862
OC=$WT/build/linux-gcc-release/one_combat
FASTF=$R2/durable/FAST-final.native
STD1E=$R2/durable/STD1-escape.native
M_FINAL=$R2/durable/candidate-v3.json      # or $R2/candidate-v3.json; the sha check decides
U=$R2/union                                # fill in if different: the union whose row_scopes.json the training used
AB=$R2/offline-ab-20261009                 # new; nothing else writes here
S0=<dir with the Stage 0 learned-arm JSONLs, or empty>   # see section 5
export OMP_NUM_THREADS=1
unset STS_CTM_PINS STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
test ! -e "$AB" && mkdir -p "$AB"/{scores,results,logs}
cand() { STS_CTM_RESEARCH_CANDIDATE_MANIFEST="$(realpath "$M_FINAL")" \
         STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256="$(sha256sum "$M_FINAL" | cut -d' ' -f1)" "$@"; }
prod() { env -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256 "$@"; }
```

* `ctmscorerows` opens its output with a plain `ofstream`, which truncates (ctm_offline_score.cpp:65). Every scoring
  command below is guarded with `test ! -e`.
* `python3 -I` keeps the script directory and the current directory off `sys.path`. The script needs only stdlib and numpy.

### Pre-flight (CPU, seconds)

```sh
sha256sum $OC | tee $AB/logs/oc.sha256
sha256sum $FASTF $STD1E $M_FINAL selfplay/models/combat_transition_deepsets_lizard_t2.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native | cut -c1-8
# expect: 90806c25 b9188de0 d9d8377e abb2a9ea e9a18951
python3 -I - "$M_FINAL" "$FASTF" "$STD1E" <<'EOF'
import hashlib, json, sys
m = json.load(open(sys.argv[1])); sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
print(m['schema'], m['candidateId'])                                         # ctm_research_candidate_v3 pathb-r2
print(sorted(m['capabilities']['standard']), sorted(m['capabilities']['fast']))   # ['escape'] ['escape']
print(m['fast']['artifactSha256'] == sha(sys.argv[2]), m['standard']['artifactSha256'] == sha(sys.argv[3]))  # True True
print(m['activeLizard'] is not None)                                          # True
EOF
$OC ctmscorerows; echo "exit=$?"     # expect the usage line with [FAST.native STANDARD.native [LIZARD=0|1]], exit=2
python3 -I - "$U" <<'EOF'
import hashlib, json, sys
u = sys.argv[1]; m = json.load(open(u + '/corpus.jsonl.manifest.json'))
h = hashlib.sha256()
with open(u + '/corpus.jsonl', 'rb') as f:
    for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
print('union rows', m['integrity']['rows'], 'sha ok', h.hexdigest() == m['csv']['sha256'])
print(json.dumps({s: r['rows'] for s, r in json.load(open(u + '/row_scopes.json')).items()}))
EOF
# expect sha ok True; five scopes: none, ritual_writhing, high_maxhp, lizard_fairy, lizard_brew
```

Stop on any mismatch. **Unverified:** that `$U` is the R2 union (the candidate's training corpus). If R2 used a different
union, every TEST seed is still unseen in fitting (the split is a pure function of the source seed). But the
`in_union` tags would then describe the wrong corpus.

## 3. Freeze the pre-registration (before any scoring)

Paste the comparison script, check its hash, and write the freeze record. **Do this before section 6.**

```sh
cat > $AB/offline_ab_compare.py <<'OFFLINE_AB_PY'
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
OFFLINE_AB_PY
sha256sum $AB/offline_ab_compare.py     # expect ff71cf537a95729018053e50bffd9e95903b1697a1a12f358565fe76b7d70005
python3 -I -c "import numpy; print(numpy.__version__)" | tee $AB/logs/numpy.version
{ date -u +%FT%TZ; git -C $WT rev-parse HEAD; sha256sum $AB/offline_ab_compare.py $OC $FASTF $STD1E $M_FINAL; } \
  > $AB/PREREG-FROZEN.txt
```

The decision constants live at the top of the script (`MARGIN_*`, `BOSS_*`, `CAND_BIAS_BAND`, ...). `compare --role gate`
refuses a different `--reps`/`--seed`/`--split` (main()). Changing any constant after this point voids the
pre-registration. A change must be made, and recorded with a reason, before the first `ctmscorerows` call.

## 4. Decision rule (pre-registered)

**Unit and resampling.** A row is one fight. The resampling unit is the source seed: a paired bootstrap with 2,000
replicates and `numpy.random.default_rng(418)`. Every row of a drawn seed is kept, and production and the candidate are
scored on the identical resample. CIs are 95% percentile intervals. Each statistic is a ratio of seed-weighted sums.

**Row populations.** These are computed on every scored set.
* *valid*: `run_valid=1` and `combat_outcome` in {1 win, 2 loss}. An escape is outcome 1 with `post.smokeBombUsed`
  (rows store PLAYER_VICTORY for escapes), so it counts as survival.
* *both*: valid and scored by both stacks. All paired deltas are computed here.
* *candOnly* / *prodOnly*: valid and scored by one stack only. These are coverage, reported with their support reasons.
* *neither*: reported with both stacks' reasons.

**Per-row metrics.** Each stack is scored on its own supported rows:
* `survival_nll` = −[y·log p + (1−y)·log(1−p)], with p = `p_death` clipped to [1e-6, 1−1e-6] and y = died;
* `brier` = (p−y)²;
* `survival_bias` = y − p (predicted P(win) minus observed win; + = optimistic);
* on wins only:
  * `hp_nll` = −max(`log_p_post_hp`, log 1e-6), which is Stage 0's floor;
  * `hp_zero` = [`log_p_post_hp` = −inf];
  * `hp_bias` = `expected_win_hp` − `post_hp`;
  * `hp_mae` = |`hp_bias`|.

Deltas are candidate minus production, so negative favours the candidate.

**Gate slice:** main scope (`forcedSetup` none), TEST split (`split_for_seed`, SHA256 of
"combat-transition-model-v1:"+seed, bucket ≥ 90), *both* population. Forced rows never enter it.

**Primary metrics:**
* ΔS = Δ`survival_nll` (all fights);
* ΔH = Δ`hp_nll` (all wins).

**Guards.** All of them must hold:
* **G1 support:** `prodOnly` ≤ 0.1% of production-supported valid rows. The candidate must not refuse rows production
  serves.
* **G2 zero-probability HP:** the candidate's `hp_zero` count on *both* wins ≤ production's count + ceil(1e-4 × wins).
* **G3 boss:** boss ΔS CI upper < +0.02 and boss ΔH CI upper < +0.10.
* **G4 calibration:** the candidate's `survival_bias` CI lies inside (−0.01, +0.01).

**Verdict** (`decision.verdict` in `results/main_test.json`):
* **FAIL** if any guard fails, or ΔS CI upper ≥ +0.005 nat/fight, or ΔH CI upper ≥ +0.03 nat/win.
* **PASS** if not FAIL, at least one of ΔS, ΔH has CI upper < 0, and neither has CI lower > 0.
* **NON_INFERIOR** otherwise: both are within the margins, but there is no strict improvement, or one is significantly
  (if slightly) worse.

**Consequence:**
* PASS: independent review of this result, then the live 128-pair A/B under its own pre-registration and the seed guard.
* NON_INFERIOR: independent review. The live A/B needs an explicit owner decision, because the only remaining benefit is
  coverage (held Smoke Bomb rows the candidate serves).
* FAIL: stop. No live A/B. Report the failing guard or margin.

**Margins (why these numbers).** On Stage 0's learned arm, production had survival NLL 0.069 nat/fight and HP NLL
2.61 nat/win (ledger §386). +0.005 is about 7% of the survival NLL. +0.03 is about 1.2% of the HP NLL. Both are half of
Stage 0's teacher-transfer tolerances (0.01, 0.05). The boss margins are wider because the boss slice is about 10× smaller.

**Secondary and diagnostic slices.** These are reported, never part of the verdict.
* Per-slice flags in `flags`:
  * `SLICE_REGRESSION:<slice>:<metric>`: a slice with ≥200 *both* rows and ≥20 seeds whose ΔS or ΔH CI lower bound is
    > 0. The slices are room × act, escaped, smoke_held, lizard_active, brew_held, fairy_held and not_in_union;
  * `CANDIDATE_ONLY_MISCALIBRATED`: ≥100 candOnly rows whose candidate `survival_bias` CI lies entirely outside ±0.05;
  * `HP_ZERO_EXCESS` (as G2).
* Forced scopes, each run separately with `--role secondary`: `ritual_writhing`, `high_maxhp`, `lizard_fairy`,
  `lizard_brew`.
* Stage 0 learned arm (section 5) with `--role replication`. Its flag is `REPLICATION_CONFLICT:<slice>:<metric>`.
* The reviewer must address every flag explicitly. A flag does not change the verdict.
* Held Smoke Bomb rows are production-unsupported (`smoke_bomb`), so they appear in `candOnly` (`candOnly.smoke_held`,
  `candOnly.escaped`). Only absolute candidate calibration exists for them. The binding escape gate stays the exposure
  run (CAPABILITIES-RUNBOOK C6/E1).

## 5. Row sets

| Set | Source | Role | Expected size (Inference: Path B cloud parts ×1.25; cloud = 560 of 700 units) |
|---|---|---|---|
| main TEST | scope `none`, TEST seeds | **gate** | ~50k rows, ~2,350 seeds, ~1,480 losses, ~5,350 boss rows, ~415 held-Smoke rows (~340 escapes) |
| ritual_writhing TEST | forced scope | secondary | ~970 rows, ~45 seeds |
| high_maxhp TEST | forced scope | secondary (no inference: ~4 seeds) | ~100 rows, ~80% with pre maxHP > 160 |
| lizard_fairy TEST | forced scope | secondary | ~1,120 rows, ~44 seeds |
| lizard_brew TEST | forced scope | secondary | ~1,600 rows, ~66 seeds |
| Stage 0 learned arm | seeds 50000000..50000127 | replication (all splits: out of sample) | 2,620 rows, 128 seeds, 87 losses, 267 boss, 11 held Smoke, 10 escapes |

* **Which scope corpora.** The assembled scope corpora (`row_scopes.json` → each scope manifest → `csv.path`), not the
  union. The union dropped rows the old candidate-contract predicate rejects, such as active-unqualified-Lizard rows and
  +14 maxHP wins (ctm_corpus_adapter.py:143-162, :164-237). Those rows are part of what the deployed stack sees. The
  `in_union` tag and the `not_in_union` slice show how much they matter.
* **TEST is unseen by fitting.** Every fit stage splits by `split_for_seed` (combat_transition_model_experiment.py:209-213,
  ctm_escape.py:174-178). **Inference:** TEST was not used for selection, but it was used for qualification gates
  (exposure, near_full_quality), which is a mild selection effect. Stage 0 is the untouched replication.
* **Stage 0 teacher.** The `learned` arm is the Path B teacher. Its teacher JSON
  (`silver-ordinary-fair-learnedstop-ctm-stage0-46153506`) has the same `search_configuration` and `environment` as Path
  B's (`...-ctm-pathb-1e1bdc09`): learned_stop, gbt-770201c31f7b, threshold 0.0323, 10k cap, allocated 32k reuse, the same
  OOC models. Only the producer SHA differs. Between `46153506` and `1e1bdc09`, `src/` changed only in two places:
  * event-fight rewards are forfeited on a Smoke Bomb escape (4f8d5548);
  * native Silver gained search statistics and a planner-seed override used only by the #347 rescue replay mode.
  
  **Inference:** that is teacher-equivalent for these rows. The `exact10k` arm is **not** the candidate's teacher. Do not
  use it here.
* **Stage 0 rows on Philipp's machine.** Only part `local` (seeds 50000000..50000042, 849 rows, 43 seeds) was produced
  there: `<stage0 worktree>/build/ctm-stage0/part-local/local-w{0..9}-learned.jsonl`. The other 85 seeds exist only in
  the project share. Use the 43-seed subset (`S0_SET=local`) unless the cloud parts are brought over (`S0_SET=all`;
  Open question Q2). Expected SHA256 (from the parts' DONE files):

```text
931e3a122e05e060b477ade827e7b7805d15352d9f5ebb771360f365a418470f  cloud1-w0-learned.jsonl
04687a8f885c61a738584ed208bcf0f1de3e82b948beb5d4679214425a3c3ea9  cloud1-w1-learned.jsonl
8fa6682363e6e4426cff9c1ff094d78b4ea6e4de174e9f9c03256afbfe9a062e  cloud1-w2-learned.jsonl
c65488a6da2c91c097d2b455c990d2fc70365e9c0c020d423c6d3b8caf30b267  cloud1-w3-learned.jsonl
99eacf516eacdc0d7fdcc57faba6266ae82680ef6199bd4c1eb1b9bd16439ccf  cloud2-w0-learned.jsonl
f8c9e855845885fb27bfaaed6b3b60221ce2aa4b9f51b40f11fd2fd87331396d  cloud2-w1-learned.jsonl
c8cc5d63ae873a676114032ffddd2ef4d005a62c665c94312fd40abd775aa8d8  cloud2-w2-learned.jsonl
6514fb953f7692c3bd0fccb04023c7960f733412aa9d285a667dafb44a33f3c7  cloud2-w3-learned.jsonl
e31240682dfb94d5aee63bed8622c6951fd3db91ffd8babbb0ef92cf8277466a  cloud3-w0-learned.jsonl
8ae43fa6511f1561a1c13f23320403cf90bfe63c8f14caca61ef0e1cac71f1ed  cloud3-w1-learned.jsonl
937b6c0dd8eefc67df999d29af991bd4575507f1979ae77127066635b2b5b2f6  cloud3-w2-learned.jsonl
c8afe2dad10869d6e6b7e64502bf80c34cfbd894f3b117d5ec3a180d9d5294c0  cloud3-w3-learned.jsonl
14a3026ddadfab730dd500320cff8c18b7f6028bebc844194da350397548a1ac  cloud4-w0-learned.jsonl
0901d2e80cd2e31eafaaabf7ab61c8b9dd78e898276f132e97ed3b2827bab195  cloud4-w1-learned.jsonl
c2da026e65c1896dcf97630b7662283fc3c68975450caab731d17485841216a5  cloud4-w2-learned.jsonl
27a797ab9209f77b601d21d6e37e4a29f0de74f98704393cb853e967ab03e8b9  cloud4-w3-learned.jsonl
ea51cd0de3b2dfa762a25ac9ca36dc915d689ccd8f762582069af90530189145  cloud5-w0-learned.jsonl
be49f27eddbabbbb3283a3b19a9494d2b37f474f98d3763073cba3f513f389cb  cloud5-w1-learned.jsonl
2f006368057869a8a5d9f5035b865fce4e9e82a104e2c3a9ced2ce125c1c9532  cloud5-w2-learned.jsonl
ae87ecd949122430a4125e8d962cebc08e808d2c179170d54394ed1cec8443eb  cloud5-w3-learned.jsonl
6865a789adbb0050aedeed981aa3eea91859ba31392d02be6233ea8b0e5b86d9  local-w0-learned.jsonl
4894bd8ca887285d91265399c0b91ad004c06e11d3889fceeb74c5ad9ed012ba  local-w1-learned.jsonl
ad969da75f5c101fad57b5210ca6dd849a2371281bc2066a969d7553115438fb  local-w2-learned.jsonl
4dd78df02a335d8844a6fad07685b2e65f0cecf831acbe7b992aca509f9d76d3  local-w3-learned.jsonl
1784d0fc8962de47705d5d1a687c9a42847c50ce56ef97ff6e17b85bf39b983c  local-w4-learned.jsonl
31be7b757319bd2e2f2ab68b70c0a7bd7ae131272eb881fc452faaa18dfc2d2a  local-w5-learned.jsonl
3a6697dae930a4369fe567a855854c4ee0535b60e843880906dc24fa68e4dc10  local-w6-learned.jsonl
d59b76f3f20503127beb2d650555913dfcfed18d5741efef76a648ae7f9700aa  local-w7-learned.jsonl
bc55b094bd3a11c3b414e419cce180997d2171ac24a6d4ceba68c5ad3355c2ab  local-w8-learned.jsonl
58234e31f54455591d98d501bfeb327b0cbca3c580b83a0e56723d9cfc17c9aa  local-w9-learned.jsonl
```

## 6. Extract TEST rows and tags (CPU; I/O bound, a few minutes)

```sh
python3 -I $AB/offline_ab_compare.py extract --union $U --out $AB 2>&1 | tee $AB/logs/extract.log
```
* For each scope, `extract` checks three things: `manifestSha256` from `row_scopes.json`, `forcedSetup` = the scope, and
  `sha256(csv.path)` = the manifest's `csv.sha256`. It writes the TEST rows to `$AB/rows/<scope>.jsonl` and the tags to
  `$AB/tags/<scope>.csv`. It refuses an existing `$AB/rows` and fails if a union TEST row is missing from its scope
  corpus.
* Check `$AB/extract.json`: `scopes.none.testRows` should be ≈ 50k (±15%), `testSeeds` ≈ 2,350, `smokeHeld` ≈ 400 and
  `escaped` ≈ 340. A large deviation means `$U` or the scope corpora are not the Path B R2 inputs. Stop and report.

Stage 0 (optional replication):
```sh
if [ -n "$S0" ]; then
  ls $S0/*-learned.jsonl | sort -V > $AB/logs/s0.files
  ( cd $S0 && sha256sum $(xargs -n1 basename < $AB/logs/s0.files) ) | tee $AB/logs/s0.sha256  # compare with section 5
  test ! -e $AB/rows/stage0_learned.jsonl && cat $(cat $AB/logs/s0.files) > $AB/rows/stage0_learned.jsonl
  python3 -I $AB/offline_ab_compare.py tag --rows $AB/rows/stage0_learned.jsonl --scope stage0_learned \
    --out $AB/tags/stage0_learned.csv
fi
```

## 7. Score (CPU; about 1 min per stack per 50k rows)

Measured on the cloud container: production `ctmscorerows` took 6.3 s for 8,000 Path B rows (0.8 ms per row, one core).
Its output for the Stage 0 shard `cloud1-w0-learned` was byte-identical to the Stage 0 score file. **Inference:** the
candidate costs about the same per row; Brew rows use the Attention child. Total ≈ 55k rows × 2 stacks ≈ 2 CPU-minutes,
with RAM under 1 GB.

```sh
for f in $AB/rows/*.jsonl; do s=$(basename $f .jsonl)
  test ! -e $AB/scores/$s.prod.csv && test ! -e $AB/scores/$s.cand.csv || { echo "exists: $s"; break; }
  prod $OC ctmscorerows $f $AB/scores/$s.prod.csv 2> $AB/logs/$s.prod.log &
  cand $OC ctmscorerows $f $AB/scores/$s.cand.csv $FASTF $STD1E 1 2> $AB/logs/$s.cand.log &
  wait
done
grep -H "ctmscorerows" $AB/logs/*.log
```
* Each `*.cand.log` must contain `ctmscorerows research candidate pathb-r2` (ctm_offline_score.cpp:60-62). No
  `*.prod.log` may contain it.
* Each log ends `ctmscorerows rows=R scored=S`. R must equal `wc -l` of the rows file for both stacks.
* A `ctmscorerows: ...` or `combat runtime ...` exception is a loader refusal (manifest SHA, bytes, capabilities,
  qualification classification, exclusions). Stop and report the message; do not work around it.
* Only these scores are produced. Do not score TRAIN or VALIDATION rows.

## 8. Compare (CPU, seconds per set)

```sh
C="python3 -I $AB/offline_ab_compare.py compare"
$C --prod $AB/scores/none.prod.csv --cand $AB/scores/none.cand.csv --tags $AB/tags/none.csv \
   --label main_test --role gate --out $AB/results/main_test.json | tee $AB/logs/main_test.summary.json
for s in ritual_writhing high_maxhp lizard_fairy lizard_brew; do
  $C --prod $AB/scores/$s.prod.csv --cand $AB/scores/$s.cand.csv --tags $AB/tags/$s.csv \
     --label ${s}_test --role secondary --out $AB/results/${s}_test.json | tee $AB/logs/${s}_test.summary.json; done
[ -n "$S0" ] && $C --prod $AB/scores/stage0_learned.prod.csv --cand $AB/scores/stage0_learned.cand.csv \
   --tags $AB/tags/stage0_learned.csv --split all --role replication --label stage0_learned \
   --out $AB/results/stage0_learned.json | tee $AB/logs/stage0_learned.summary.json
```
* `compare` refuses these cases:
  * CSVs that do not cover the same rows;
  * differing label fields (seed through post maxHP);
  * a header that is not ctmscorerows';
  * non-TEST seeds under `--split test`;
  * an existing `--out`.
* `results/<set>.json` holds:
  * `census`: populations, support-reason cross-tabs and zero-probability counts;
  * `both.<slice>.{production,candidate,candidateMinusProduction}.<metric>` = {mean, ci95, n, seeds};
  * `candOnly.<slice>` and `prodOnly.<slice>`;
  * `flags`;
  * for the gate, `decision`;
  * input and script SHA256s, the numpy version and the constants.
* Sanity anchor: production's metrics on the Stage 0 learned arm reproduce ledger §386 (survival NLL 0.0688, HP NLL 2.611,
  survival bias −0.0008, boss HP bias +10.03; checked on the cloud copy with this script).

## 9. Hand-back

```sh
tar czf $AB.tgz -C $(dirname $AB) $(basename $AB)/{PREREG-FROZEN.txt,extract.json,results,logs,scores,tags,offline_ab_compare.py}
sha256sum $AB.tgz
```
Return the tarball (rows are excluded; they can be regenerated from the corpora). Report:
* the `decision` block of `main_test.json`;
* `census` of every set;
* every flag.

The independent review reads the tarball. The live A/B is planned only after that review.

## Hazards

* **H1 Loader refusals are fail-closed.** These all throw before any row is scored:
  * a wrong `$M_FINAL` or its SHA256;
  * a candidate artifact whose bytes or capabilities are not in the manifest;
  * a standard artifact without `FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS`;
  * a fast/standard escape mismatch.

  Production, scored with the variables unset, cannot load candidate bytes. A non-stamped artifact always uses the
  production identity (runtime.cpp:366).
* **H2 Relative production paths.** The two-argument form loads `selfplay/models/...` relative to the current directory
  (driver_shared.h:411-412). Run from `$WT`; the pre-flight hash check covers the files.
* **H3 `log_p_post_hp` = −inf.** The scorer writes −inf when the observed post HP falls outside the histogram or has
  zero mass (ctm_offline_score.cpp:111-115). The metrics floor it at log 1e-6, as Stage 0 did, and count it
  (`census.hpZeroBoth`, guard G2). Stage 0 had none for production. The candidate's widened HP domain gives new classes
  a bias of −30 (ctm_hp_domain expand), which is small but not zero.
* **H4 Escapes are wins.** `combat_outcome` is 1 for an escape (smokeBombUsed). The ctmscorerows CSV has no escape
  column; escapes come from the tags.
  * Stage 0's analyze.py counted escapes as `combat_outcome == 0`. So ledger §386's "There were no escapes" is wrong:
    the learned/exact arms have 10/15 escaped rows (11/16 held-Smoke rows).
  * All of them were production-unsupported (`smoke_bomb`), so the §386 metrics are unaffected. The ledger wording
    needs a later correction (Knowledge impact).
* **H5 What a PASS means.** Production was trained on the old exact-10k `f0bbd77` teacher corpus. Path B TEST and Stage 0
  rows come from the learned-stop teacher, which ends boss wins about 13 HP lower (§386). The candidate is therefore
  expected to win on HP NLL. A PASS shows the candidate fits the current teacher better. It does not show that the
  candidate plays better; the live A/B decides that.
* **H6 Tags are approximate.** The tags use enum ordinals at `7d62ba42`: SMOKE_BOMB=37, ENTROPIC_BREW=17, FAIRY_POTION=21,
  LIZARD_TAIL=35, and boss = `roomClass` BOSS. They define diagnostic slices only, not the gate.
* **H7 Bootstrap determinism.** Results depend on numpy's PCG64 stream. The numpy version is recorded. **Inference:**
  `Generator.integers` is stable across numpy 1.17+ for this use.
* **H8 high_maxhp has ~4 TEST seeds.** It gives no inference. Its rows are mostly candOnly (production envelope ≤ 160).
  The candidate has no `highMaxHp` capability flag; the declared domain covers it.

## Open questions (owner, before section 6)

1. **Margins.** Are +0.005 nat/fight (ΔS) and +0.03 nat/win (ΔH), with the boss guards +0.02/+0.10 and the calibration
   band ±0.01, acceptable? Change them only before scoring (section 3).
2. **Stage 0 cloud parts.** Should the 85-seed cloud part of the Stage 0 learned arm be brought to this machine, so the
   replication uses all 128 seeds? Alternatively, should the candidate's three files (about 4 MB) be returned to the
   project share, so a cloud session scores Stage 0 there? The production Stage 0 scores already exist in
   `ctm-stage0/analysis/scores/`.
3. **NON_INFERIOR.** Is coverage alone (held Smoke Bomb, wider HP domain) enough to proceed to the live A/B?
4. **Paths.** `$U` (assumed `$R2/union`), the location of `$M_FINAL` (`durable/` or R2 root), and the Stage 0 local
   part's directory.
