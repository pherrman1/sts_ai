# Training and inference

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Pipeline

The implemented learning loop is:

1. `one_combat` modes generate run, combat-value, policy-edge, paired-action,
   or oracle CSV rows (`apps/one_combat.cpp`, `main`, including `datagen3`,
   `fightgen`, `fairgen`, `oocnextgen`, and `strategicgen`).
2. Root Python trainers load CSVs, split by a run/fight/decision grouping, and
   fit XGBoost, scikit-learn, or PyTorch models (for example
   `train_winrate.py`, top-level program; `train_value_combat.py`, top-level
   program; `train_policy.py`, top-level program;
   `train_combat_pvnet.py`, `PolicyValueNet`).
3. Exporters or trainer export sections write XGBoost JSON, PyTorch checkpoint/
   TorchScript, binary MLP, or compact native tree/text artifacts
   (`export_combat_model.py`, top-level exporter;
   `export_win_model.py`, top-level exporter;
   `export_ooc_checkpoint.py`, top-level exporter;
   `train_combat_pvnet.py`, native export section).
4. `one_combat` loads compact artifacts in-process, or sends rich features to
   `v_server.py` for optional experimental inference (`apps/one_combat.cpp`,
   `main`, `WinNet::load`, `vSendRecv`; `v_server.py`, `H.handle`).
5. Combat inference influences leaf values and/or search priors; OOC inference
   scores run states or legal actions (`src/sim/search/BattleScumSearcher3.cpp`,
   `evaluateLeaf`, `computeEdgePriors`; `apps/one_combat.cpp`,
   `runFullRunOOC`).

## Data generation hooks

`ScumSearchAgent2` exposes thread-local callbacks at combat decision snapshots
and after Searcher2/Searcher3 root search
(`include/sim/search/ScumSearchAgent2.h`, `g_onCombatDecision`,
`g_onSearchComplete`, `g_onSearchComplete3`). `fightgen` uses these hooks to
emit both value snapshots labelled by fight outcome and policy rows labelled by
root visits in one combat pass when Searcher2 is active. `fightgen` does not
install `g_onSearchComplete3`, so enabling Searcher3 would omit its policy rows
(`apps/one_combat.cpp`, `fightgen` generation section and callback assignments).
`runDataGen2Seed` produces rich run outcomes
and paired strategic counterfactual rows (`apps/one_combat.cpp`,
`runDataGen2Seed`).

The combat schema is 1,766 state features plus 14 action features, with
metadata/labels around them (`DATA_SCHEMA.md`, “File 1” and “File 2”;
`src/sim/search/CombatValueNet.cpp`, `combatFeatureNames`,
`combatExtractFeatures`, and `combatFillActionFeatures`).
The rich OOC schema is serialized by `vFeatCsv` and mirrored by the 1,017-field
layout in `v_server.py` (`apps/one_combat.cpp`, `vFeatCsv`; `v_server.py`, raw
feature layout).

Two policy action features, `aPlayOrder` and `aObtainWeight`, come from the
hand-authored `Expert` tables. The deployed learned prior therefore is not an
expert-feature-free policy even though its target is learned from visits
(`src/sim/search/CombatValueNet.cpp`, `combatFillActionFeatures`;
`src/sim/search/ExpertKnowledge.cpp`).

## Split and leakage rules

Training keeps correlated rows together. Win-rate data splits by seed
(`train_winrate.py`, `GroupShuffleSplit` using `run`); combat value splits by
fight (`train_value_combat.py`, `group` and `GroupShuffleSplit`); policy splits
by complete decision group (`train_policy.py`, `group` and
`GroupShuffleSplit`); OOC checkpoint training splits whole
`(seed, decisionIdx)` groups (`train_ooc_checkpoint.py`, `groups`, `tr_groups`).
Changing these keys risks train/validation leakage.

## Trainer families

- Run values: `train_value_rich.py`, `train_winrate.py`,
  `train_boss_survival.py`, `train_deckset.py`, and
  `train_meta_entity.py` top-level programs.
- Strategic action/counterfactual models: `train_rest_cf.py`,
  `train_card_cf.py`, `train_path_cf.py`, `train_ooc_next_action.py`,
  `train_ooc_encounter.py`, and `train_ooc_checkpoint.py` top-level programs.
- Combat values: `train_value_combat.py`,
  `train_value_combat_entity.py`, `train_value_combat_mlp.py`,
  `train_value_combat_nn.py`, `train_combat_transition_entry.py`, and
  `train_combat_dist.py` top-level programs.
- Combat policies and joint models: `train_policy.py`,
  `train_policy_entity.py`, and `train_combat_pvnet.py`
  (`PolicyValueNet`). `preprocess_pvnet_data.py` prepares memory-mapped PVNet
  input.

These are executable scripts rather than an installed Python package. There is
no repository dependency lock or unified trainer CLI.

## Self-play orchestration

`selfplay/loop.sh` resumes from `selfplay/state.env`, performs `datagen3` plus
`fightgen`, retrains the meta/rest, combat-value, and policy arms, and gates
them in nominally independent common-seed arms (`selfplay/loop.sh`, generation
section, training section, and “ADAPTIVE PAIRED GATES”). Candidate promotion requires a
lower confidence bound above the configured margin; a hard-cap inconclusive
candidate is rejected (`selfplay/loop.sh`, `gate_stats` and hard-cap branch).

**Blocking discrepancy:** every meta arm starts a server with its candidate
V_win/rest files, but the invoked `one_combat` defaults native OOC on. Native
card/shop/rest code uses fixed `build/v_win_trees.txt`, and
`vQueryRestCounterfactual` immediately returns false. Because `POLICY_ENV` does
not set `STS_NATIVE_OOC=0` or an arm-specific native win artifact, the current
meta gate does not establish that it evaluated the candidate
(`selfplay/loop.sh`, `FLOOR_POLICY_ENV`, `WIN_POLICY_ENV`, `start_server`;
`apps/one_combat.cpp`, native startup, `vQueryHealWin`,
`vQueryUpgradeWin`, `vQueryRestCounterfactual`).

`selfplay/config.env` currently records 400 deployment simulations, 600 gate
simulations, 500 maximum gate seeds, a 2.58 bound multiplier, `POLICY_WINDOW=1`,
`PROMOTE_MARGIN=0.5`, and `VALUE_MARGIN=-0.5`. These are a checked-in snapshot;
the shell defaults and environment overrides remain the actual execution
mechanism (`selfplay/loop.sh`, variable initialization and config snapshot
write).

`gate_stats` uses a normal-theory mean +/- `Z*SE` interval at every adaptive
look without a repeated-look correction. Thus `Z=2.58` is nominally about 99%
for one fixed look, not a demonstrated 99% sequential guarantee. The snapshot's
`VALUE_MARGIN=-0.5` applies to every value candidate; the script does not test
whether a candidate is actually latency-oriented (`selfplay/loop.sh`,
`gate_stats`, value gate call).

**Discrepancy:** the header comments in `selfplay/loop.sh` describe whole-agent,
all-or-nothing promotion, but the implemented gate section promotes meta,
value, and policy independently and can defer policy after a simultaneous
value promotion (`selfplay/loop.sh`, header and independent promotion block).

The loop is not bootstrapped by CMake: it invokes `./one_combat.elf`, requires
server/training dependencies, and skips first-run model copying whenever
`selfplay/state.env` exists. In this checkout the state file exists, the
`current/` and other core loop directories are absent, and the first-run copy
sources `build/v_combat_fair_trees.txt` and
`build/policy_fair_trees_c.txt` are also absent (`selfplay/loop.sh`, startup and
initialization; current filesystem inspection). The checked-in snapshot cannot
be treated as runnable without repair.

## Artifacts and inference

Tracked deployed artifacts include native floor/win trees, their XGBoost JSON
sources, the compact policy trees, and a PVNet text artifact under `build/`.
The `build/` directory also contains ignored CMake output, so “under build” does
not imply generated or untracked (`.gitignore`, `/build/`; tracked files
`build/v_rich_trees.txt`, `build/v_win_trees.txt`,
`build/policy_trees_c.txt`, `build/v_combat_pvnet.txt`).

`v_server.py` binds only `127.0.0.1` on port 5555 by default and dispatches a
line protocol in `H.handle` (`v_server.py`, `PORT`, `Server`, `H.handle`). Native
OOC is enabled by default in `one_combat`; server endpoints remain necessary
for some optional neural and paired-action experiments
(`apps/one_combat.cpp`, `main`; `v_server.py`, optional model loaders).

## Relevant code

- `apps/one_combat.cpp` — generation modes, callbacks, model loading, and live inference.
- `include/sim/search/ScumSearchAgent2.h` — data-generation hooks.
- `src/sim/search/CombatValueNet.cpp` — canonical combat schema/native inference.
- `train_winrate.py`, `train_value_combat.py`, `train_policy.py` — representative grouped trainers.
- `train_combat_pvnet.py` — `PolicyValueNet` and native export.
- `train_ooc_checkpoint.py` and `export_ooc_checkpoint.py` — unified OOC action model pipeline.
- `selfplay/loop.sh` — resumable train/gate orchestration.
- `v_server.py` — optional inference service.
