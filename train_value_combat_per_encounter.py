#!/usr/bin/env python3
"""Per-encounter fine-tuning of the pooled V_combat XGBoost model.

Loads a pooled model (train_value_combat.py output, e.g.
build/v_combat_hparam.json), then for each requested encounter continues
boosting on that encounter's rows only:

    xgb.train(params, dtr, xgb_model=pooled_bst, num_boost_round=N,
              evals=[(dva, "val")], early_stopping_rounds=10)

The per-encounter model inherits every pooled tree and adds up to N
encounter-specialized trees (early stopping prunes back to the best). Rows,
fight-group split, critical-state weights, feature columns (the pooled model's
own feature_names, so the booster can be continued), and QuantileDMatrix
construction follow train_value_combat.py.

Exports per-encounter models as compact-tree text files named
<ENCOUNTER_NAME>.txt (the C++ CombatValueNet::loadEncounterModels enum-name
convention) plus the pooled baseline as _pooled.txt and a per-encounter
validation CSV (<NAME>_val.csv, canonical features + pyPred) for
`one_combat vnettest --encounter <NAME>`.

Usage:
  python3 train_value_combat_per_encounter.py [csv] [pooled_model.json]
      [outdir] [rounds] [encounter...]

Environment:
  STS_XGB_DEVICE       device override ("cuda"/"cpu"; default auto-detect)
  VCOMBAT_TARGET       label: endhp (default) or utility_r
  VCOMBAT_WIN_BONUS    win bonus for utility_r (default 50)
  PER_ENC_POLICY_CSV   optional teacher-disagreement CSV (same recipe as the
                       pooled trainer's third positional arg)
  PER_ENC_CONSERVATIVE=1  tail-encounter recipe: N=15 rounds and stronger
                       regularization (reg_alpha/gamma bumped) — the
                       "conservative fine-tuning" approximation to
                       meta-learning for sparse/rare encounters
"""
import sys, os, json, shutil, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
import export_combat_model as exporter

CSV     = sys.argv[1] if len(sys.argv) > 1 else "build/vcombat.csv"
POOLED  = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_hparam.json"
OUTDIR  = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_per_encounter"
ROUNDS  = int(sys.argv[4]) if len(sys.argv) > 4 else 50
ENCARGS = sys.argv[5:]

TARGET = (os.environ.get("VCOMBAT_TARGET") or "endhp").strip().lower()
if TARGET not in ("endhp", "utility_r"):
    raise SystemExit(f"VCOMBAT_TARGET must be 'endhp' or 'utility_r', got {TARGET!r}")
WIN_BONUS = float(os.environ.get("VCOMBAT_WIN_BONUS", "50"))
LABEL_NAME = "utility R" if TARGET == "utility_r" else "endHp"
CONSERVATIVE = os.environ.get("PER_ENC_CONSERVATIVE", "0") == "1"
POLICY_CSV = os.environ.get("PER_ENC_POLICY_CSV", "")

# Default encounter list: the 10 bosses named by MonsterEncounters.h
# isBossEncounter(). Override with positional encounter names.
BOSSES = ["SLIME_BOSS", "THE_GUARDIAN", "HEXAGHOST", "AUTOMATON", "COLLECTOR",
          "CHAMP", "AWAKENED_ONE", "TIME_EATER", "DONU_AND_DECA", "THE_HEART"]
ENCOUNTERS = ENCARGS or BOSSES
# Map enum name -> int (mirror of monsterEncounterEnumNames in C++).
_ENUM_INT = {name: i for i, name in enumerate([
    "INVALID","CULTIST","JAW_WORM","TWO_LOUSE","SMALL_SLIMES","BLUE_SLAVER",
    "GREMLIN_GANG","LOOTER","LARGE_SLIME","LOTS_OF_SLIMES","EXORDIUM_THUGS",
    "EXORDIUM_WILDLIFE","RED_SLAVER","THREE_LOUSE","TWO_FUNGI_BEASTS",
    "GREMLIN_NOB","LAGAVULIN","THREE_SENTRIES","SLIME_BOSS","THE_GUARDIAN",
    "HEXAGHOST","SPHERIC_GUARDIAN","CHOSEN","SHELL_PARASITE","THREE_BYRDS",
    "TWO_THIEVES","CHOSEN_AND_BYRDS","SENTRY_AND_SPHERE","SNAKE_PLANT",
    "SNECKO","CENTURION_AND_HEALER","CULTIST_AND_CHOSEN","THREE_CULTIST",
    "SHELLED_PARASITE_AND_FUNGI","GREMLIN_LEADER","SLAVERS",
    "BOOK_OF_STABBING","AUTOMATON","COLLECTOR","CHAMP","THREE_DARKLINGS",
    "ORB_WALKER","THREE_SHAPES","SPIRE_GROWTH","TRANSIENT","FOUR_SHAPES",
    "MAW","SPHERE_AND_TWO_SHAPES","JAW_WORM_HORDE","WRITHING_MASS",
    "GIANT_HEAD","NEMESIS","REPTOMANCER","AWAKENED_ONE","TIME_EATER",
    "DONU_AND_DECA","SHIELD_AND_SPEAR","THE_HEART","LAGAVULIN_EVENT",
    "COLOSSEUM_EVENT_SLAVERS","COLOSSEUM_EVENT_NOBS","MASKED_BANDITS_EVENT",
    "MUSHROOMS_EVENT","MYSTERIOUS_SPHERE_EVENT"])}

# §148 hyperparameter-tuned defaults (same recipe as train_value_combat.py).
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
PARAMS = dict(objective="reg:squarederror", tree_method="hist", device=DEVICE,
              max_depth=8, eta=0.03, subsample=0.54, colsample_bytree=0.81,
              min_child_weight=82, max_bin=256, reg_alpha=1.8, gamma=4.4)
if CONSERVATIVE:
    ROUNDS = 15
    PARAMS["reg_alpha"] = 6.0
    PARAMS["gamma"] = 10.0

pooled = xgb.Booster()
pooled.load_model(POOLED)
feats = list(pooled.feature_names)
nfeat = len(feats)
print(f"pooled model: {POOLED} ({nfeat} features, "
      f"{len(pooled.get_dump())} trees); continuing on {DEVICE}", flush=True)
print(f"fine-tuning {len(ENCOUNTERS)} encounters: {ENCOUNTERS} "
      f"({ROUNDS} rounds, conservative={CONSERVATIVE}, target {LABEL_NAME})", flush=True)

print(f"loading {CSV} ...", flush=True)
_hdr = pd.read_csv(CSV, nrows=0).columns
dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in _hdr}
df = pd.read_csv(CSV, dtype=dtypes)
N = len(df)
group = (df["seed"].to_numpy(np.int64) * 1000 + df["fightIdx"].to_numpy(np.int64))
header = list(df.columns)

# Critical-state weights (same recipe as train_value_combat.py): failed fights,
# low-HP states, empirically lethal encounters, teacher disagreement.
won = df["won"].to_numpy(np.float32)
hp_frac = (df["curHp"].to_numpy(np.float32)
           / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
fights = df[["seed", "fightIdx", "encounter", "won"]].drop_duplicates(["seed", "fightIdx"])
enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
disagreement = np.zeros(N, dtype=np.float32)
if POLICY_CSV and os.path.exists(POLICY_CSV):
    print(f"loading teacher disagreement from {POLICY_CSV} ...", flush=True)
    p = pd.read_csv(POLICY_CSV, usecols=["seed", "fightIdx", "decIdx", "visit", "total"],
                    dtype={"seed": np.int32, "fightIdx": np.int32, "decIdx": np.int32,
                           "visit": np.int32, "total": np.int32})
    decision = df.groupby(["seed", "fightIdx"], sort=False).cumcount().to_numpy(np.int64)
    pkey = (p["seed"].to_numpy(np.int64) * 100000
            + p["fightIdx"].to_numpy(np.int64) * 1000 + p["decIdx"].to_numpy(np.int64))
    p["_key"] = pkey
    pg = p.groupby("_key", sort=False).agg(best=("visit", "max"), total=("total", "first"))
    ambiguity = (1.0 - pg["best"] / np.maximum(pg["total"], 1)).astype(np.float32)
    decision_key = (df["seed"].to_numpy(np.int64) * 100000
                    + df["fightIdx"].to_numpy(np.int64) * 1000 + decision)
    mapped = pd.Series(decision_key).map(ambiguity)
    present = mapped.notna().to_numpy()
    disagreement[present] = mapped[present].to_numpy(np.float32)
weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)
          + 1.5 * enc_fail + 1.5 * disagreement)
weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
weight /= weight.mean()

# Label: endHp or terminal utility R (same convention as the pooled trainer).
endhp = df["endHp"].to_numpy(np.float32)
if TARGET == "utility_r":
    y = np.where(won >= 0.5, np.float32(WIN_BONUS) + endhp, np.float32(0.0)).astype(np.float32)
else:
    y = endhp
Xfull = df[feats].to_numpy(np.float32)
enc_col = df["encounter"].to_numpy(np.int16)

os.makedirs(OUTDIR, exist_ok=True)
print(f"data: {N} rows, {len(np.unique(group))} fights; target {LABEL_NAME}", flush=True)

# Pooled baseline export (the _pooled.txt fallback for non-specialized encounters).
pooled_json = os.path.join(OUTDIR, "_pooled.json")
pooled.save_model(pooled_json)
exporter.export_trees(pooled_json, os.path.join(OUTDIR, "_pooled.txt"))

# Validation writer: canonical features + this model's pyPred on a sample of the
# encounter's own rows (200, like the pooled export), so
# `one_combat vnettest --encounter <NAME>` can check parity.
def write_encounter_val(samp_df, bst, ntrees, out_path):
    canon = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")]
    samp = samp_df.sample(frac=1, random_state=1).reset_index(drop=True)
    samp = samp.head(200)
    Xmodel = samp[feats].to_numpy(np.float32)
    pred = bst.predict(xgb.DMatrix(Xmodel, feature_names=feats),
                       iteration_range=(0, ntrees))
    out = samp[canon].copy()
    out["pyPred"] = pred
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path}: {len(out)} rows (pred mean {pred.mean():.2f})", flush=True)

for name in ENCOUNTERS:
    if name not in _ENUM_INT:
        print(f"WARNING: unknown encounter name {name!r}; skipping")
        continue
    enc = _ENUM_INT[name]
    mask = enc_col == enc
    if not mask.any():
        print(f"WARNING: encounter {name} has no rows in {CSV}; skipping")
        continue
    Xe = Xfull[mask]; ye = y[mask]; ge = group[mask]; we = weight[mask]
    dfe = df[mask]
    nfights = len(np.unique(ge))
    print(f"\n=== {name} (enum {enc}): {len(Xe)} rows, {nfights} fights ===", flush=True)
    if nfights < 2:
        print("  too few fights to split; using all rows for training "
              "(no early stopping)", flush=True)
        dtr = xgb.QuantileDMatrix(Xe, label=ye, weight=we, feature_names=feats)
        bst = xgb.train(PARAMS, dtr, num_boost_round=ROUNDS, xgb_model=pooled,
                        verbose_eval=False)
        ntrees = len(bst.get_dump())
    else:
        tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0)
                      .split(Xe, ye, groups=ge))
        dtr = xgb.QuantileDMatrix(Xe[tr], label=ye[tr], weight=we[tr], feature_names=feats)
        dva = xgb.QuantileDMatrix(Xe[va], label=ye[va], weight=we[va], ref=dtr,
                                  feature_names=feats)
        bst = xgb.train(PARAMS, dtr, num_boost_round=ROUNDS, evals=[(dva, "val")],
                        early_stopping_rounds=10, xgb_model=pooled, verbose_eval=False)
        ntrees = len(bst.get_dump())
    # Inherited pooled trees + added specialized trees.
    added = ntrees - len(pooled.get_dump())
    print(f"  trained: {ntrees} total trees (+{added} encounter-specialized)", flush=True)
    json_path = os.path.join(OUTDIR, name + ".json")
    bst.save_model(json_path)
    exporter.export_trees(json_path, os.path.join(OUTDIR, name + ".txt"))
    write_encounter_val(dfe, bst, ntrees, os.path.join(OUTDIR, name + "_val.csv"))

print(f"\nDone: per-encounter models in {OUTDIR} "
      f"(set STS_VNET_PER_ENCOUNTER={OUTDIR})", flush=True)
