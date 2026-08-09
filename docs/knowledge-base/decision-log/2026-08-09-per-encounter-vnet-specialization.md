# 2026-08-09 — Per-encounter combat value specialization (per-boss fine-tune + Reptile meta-learner)

Date: 2026-08-09
Session/task: Implement two experimental improvements to the combat value
model — per-boss XGBoost fine-tuning and Reptile-style meta-learning for tail
encounters — with a shared runtime per-encounter dispatch.

## Decision

1. **One runtime dispatch map for both arms.** `CombatValueNet` gains
   `std::unordered_map<int, CombatValueNet> encounterModels` and
   `hasEncounterModels`; `predict(bc)` dispatches to
   `encounterModels[(int)bc.encounter]` when present and otherwise keeps the
   base path. When no per-encounter models are loaded this is a single bool
   test — byte-identical default behavior. `predictVec`/`predictOutcomeVec`
   are unchanged (dispatch only in the `BattleContext` overload).

2. **Arm 1 — per-boss XGBoost fine-tuning.** New
   `train_value_combat_per_encounter.py`: continues the pooled model on each
   boss's rows (`xgb_model=pooled_bst`, 50 extra rounds, early stop 10;
   `PER_ENC_CONSERVATIVE=1` = 15 rounds + bumped reg for tail encounters),
   using the pooled model's own `feature_names`, fight-group split,
   critical-state weights and QuantileDMatrix recipe. Exports
   `<ENUM_NAME>.txt` + `_pooled.txt` + per-encounter val CSV.
   `export_combat_model.py --per-encounter <dir>` converts a directory of
   `.json` models without retraining (byte-identical output).

3. **Arm 2 — Reptile meta-learning.** New `train_value_combat_meta.py`: dense
   MLP with a Reptile outer loop (clone θ, K inner SGD steps per encounter,
   θ ← θ + ε·(θ′_e − θ)/B), then offline adaptation of tail encounters
   (rows ≤ `META_TAIL_MAX_ROWS`) producing per-encounter weight deltas.
   Exports `combat_mlp_meta_v1` (base dense MLP + `dw1..db3` delta table);
   C++ reconstructs adapted weights as base + delta.

4. **`STS_VNET_PER_ENCOUNTER=<dir>`** parses after the STS_VNET / fair-S3
   default block; a missing/invalid dir warns and keeps the pooled base.
   `one_combat vnettest --encounter <NAME>` checks per-encounter parity
   (in-file delta first, then the dir overlay).

5. **ReLU, not GELU, for the meta MLP** — the native `combat_mlp_v1` C++
   path (`CombatValueNet::predictVec`) uses ReLU; a GELU-trained export would
   silently mispredict at inference. **Inference** (no experiment): GELU
   trained weights under ReLU inference differ systematically for negative
   pre-activations, which the asserting `vnettest` parity check would catch.

## Rationale

The pooled vnet splits on the encounter one-hot and cannot deeply specialize
per boss; §126 found a binary boss-only gate flat, which does not falsify
per-boss model specialization. Both arms are infrastructure with parity
evidence; no gameplay claim is made before a paired gate.

## Alternatives considered

- Online fast adaptation at inference — rejected: gradient descent per
  encounter at search time is too expensive; per-encounter models are
  pre-adapted offline.
- Per-encounter model selection via separate executable mode — rejected: the
  `encounterModels` map inside `CombatValueNet` reuses the existing
  `predict(bc)` call sites (Searcher2/Searcher3 leaf values) unchanged.
- `std::shared_ptr<CombatValueNet>` for map values — rejected: C++17
  `std::unordered_map<int, CombatValueNet>` with a recursive member is
  well-formed and simpler; each instance carries an empty map.

## Evidence

- `include/sim/search/CombatValueNet.h`, `src/sim/search/CombatValueNet.cpp`
  (`loadEncounterModels`, `combat_mlp_meta_v1` in `load`, `predict`)
- `apps/one_combat.cpp::main` (`STS_VNET_PER_ENCOUNTER` block, `vnettest`
  `--encounter`, BEST stack banner)
- `train_value_combat_per_encounter.py`, `train_value_combat_meta.py`,
  `export_combat_model.py` (`export_trees`/`write_validation`/`--per-encounter`)
- Parity: `vnettest --encounter SLIME_BOSS` max|diff| 6.7e-5 (trees) and
  1.1e-5 (meta delta reconstruction); `ctest` 9/9;
  `vnettest_selftest.py --self-test` PASS; 8-seed S3-fair smokes with and
  without `STS_VNET_PER_ENCOUNTER` show the expected load messages.
- EXPERIMENTS.md §150; `docs/knowledge-base/architecture/{combat-search,
  training-and-inference}.md`, `evaluation/current-baselines.md`.

## Status and follow-up

Implemented opt-in, gate pending: paired 64-seed per-boss gate vs the §148
pooled default; conservative fine-tuning gate for tail encounters; memory
(full tree copies per encounter) revisited only if the arm survives its gate.
