#!/usr/bin/env python3
"""Focused invariants for the E2c analyzer: manifest fail-closed, hidden exclusion,
pairing integrity, and contiguous held-out-seed bootstrap reuse."""
import importlib.util
import pathlib

import numpy as np
import pandas as pd

path = pathlib.Path(__file__).with_name("analyze_postcombat_raw_terminal.py")
spec = importlib.util.spec_from_file_location("e2c", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

header = ["seed", "fight_index", "boundary", "room_type", "encounter_id",
          "act", "floor", "curHp", "maxHp", "won", "finalFloor", "endHp",
          "nextEliteId", "nextFight0", "fmDElite", "relic_has_7", "relic_data_7",
          "d3", "u4", "mystery_col"]
man, hidden = mod.manifest(header)
by = {r["feature"]: r for r in man}
assert "nextEliteId" in hidden and by["nextEliteId"]["family"] == "hidden_rng_or_true_future"
assert by["nextFight0"]["family"] == "hidden_rng_or_true_future"
assert by["fmDElite"]["family"] == "observable_or_trackable"          # map topology visible
assert by["act"]["family"] in ("observable_or_trackable", "metadata/control")
assert by["won"]["family"] == "label"
assert by["seed"]["family"] == "metadata/control"
assert by["relic_has_7"]["family"] == "observable_or_trackable"
assert by["relic_data_7"]["family"] == "observable_or_trackable"
assert by["d3"]["family"] == "observable_or_trackable"
assert by["mystery_col"]["family"] == "ambiguous"                       # fail-closed

T = mod.t_features(header, use_counter=True)
assert "nextFight0" not in T and "nextEliteId" not in T                 # hidden excluded
assert "relic_data_7" in T and "relic_has_7" in T
assert "mystery_col" not in T                                           # ambiguous excluded
assert "room_type" in T and "encounter_id" in T                         # legit context retained
Tn = mod.t_features(header, use_counter=False)
assert "relic_data_7" not in Tn and "relic_has_7" in Tn                 # ownership-only ablation
assert "r7" not in T and "r7" not in Tn                                # legacy counter encoding cannot leak
rewards = {"gold": 0, "relic": 0, "potion": 0, "emerald": True, "sapphire": False, "cards": 1}
assert mod.post_boundary_ready("REWARDS", rewards, False)                  # key-off must not block POST
assert not mod.post_boundary_ready("REWARDS", rewards, True)               # key-on consumes the key first

# Pairing integrity: pivoting by (seed, fight_index) must cross RAW/POST labels.
df = pd.DataFrame({
    "seed": [1, 1, 1, 1, 2, 2, 2, 2],
    "fight_index": [0, 0, 1, 1, 0, 0, 1, 1],
    "boundary": ["RAW", "POST", "RAW", "POST", "RAW", "POST", "RAW", "POST"],
    "won": [1, 1, 0, 0, 1, 1, 1, 1],
    "room_type": ["MONSTER", "MONSTER", "ELITE", "ELITE", "BOSS", "BOSS", "MONSTER", "MONSTER"],
})
piv = df.pivot_table(index=["seed", "fight_index"], columns="boundary", values="won", aggfunc="first")
assert not piv["RAW"].isna().any() and not piv["POST"].isna().any()     # every pair both boundaries
assert (piv["RAW"] == piv["POST"]).all()                                # identical labels within pair

# Contiguous held-out seed bootstrap: arbitrary global seed IDs must be reindexed.
seeds = np.array([100, 100, 700, 700, 1200, 1200])
_, contiguous = np.unique(seeds, return_inverse=True)
assert list(contiguous) == [0, 0, 1, 1, 2, 2]

# Duplicate pair keys must be rejected before any pivot/aggfunc can hide them.
dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
assert dup.duplicated(["seed", "fight_index", "boundary"]).any()

# Exact preregistered verdict ordering.
checks = {"T-raw_logloss_below_B2-raw": True,
          "T-raw_brier_below_B2-raw": True,
          "T-raw_auc_above_B2-raw": True,
          "bootstrap_logloss_ci_below_zero": True,
          "T-raw_ece_le_0.10": True,
          "raw_retention_ge_0.50": True}
assert mod.classify_verdict(checks, 0.1) == "E2C SUPPORTED"
checks["raw_retention_ge_0.50"] = False
assert mod.classify_verdict(checks, 0.1) == "E2C PARTIAL"
checks["bootstrap_logloss_ci_below_zero"] = False
assert mod.classify_verdict(checks, 0.1) == "E2C NEGATIVE"
assert mod.classify_verdict(checks, 0.0) == "E2C INCONCLUSIVE"

print("postcombat raw-terminal selftest: PASS")
