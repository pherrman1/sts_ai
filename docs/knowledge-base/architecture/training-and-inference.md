# Training and inference

Last verified: 2026-07-31 against commit `67320b3` and the current working tree.

## Purpose

Document dataset producers, feature/group contracts, trainer/export paths, and
runtime model-loading interfaces without treating experimental artifacts as
active defaults merely because they are present.

## Current implementation

The learning pipeline is executable scripts rather than an installed Python
package:

1. `one_combat` modes emit run, combat, policy-edge, strategic-action, paired,
   or oracle CSV rows (`apps/one_combat.cpp::main`).
2. Root `train_*.py` programs fit XGBoost, scikit-learn, or PyTorch models.
3. `export_*.py` programs and trainer export blocks write JSON, compact tree
   text, native neural text/binary, TorchScript, or checkpoints.
4. `one_combat` loads compact artifacts in-process; optional experiments query
   `v_server.py` over localhost.
5. Model predictions supply combat priors/leaves or score run states/actions.

Representative producers are `datagen3`, `fightgen`, `fairgen`, `oocnextgen`,
and the July 31 `strategicgen` mode. `strategicgen` records one rich-state row
per OOC decision with screen/action metadata and terminal run labels
(`apps/one_combat.cpp::runStrategicGenSeed`, `strategicGen`).

Representative model families:

- run values: `train_value_rich.py`, `train_winrate.py`;
- paired/action OOC: `train_rest_cf.py`, `train_card_cf.py`,
  `train_path_cf.py`, `train_ooc_next_action.py`, `train_ooc_checkpoint.py`;
- combat value: `train_value_combat.py`, entity/MLP/distribution variants;
- combat policy/joint: `train_policy.py`, `train_policy_entity.py`,
  `train_combat_pvnet.py::PolicyValueNet`.

Runtime interfaces and their default/experimental status are summarized in
[evaluation/current-baselines.md](../evaluation/current-baselines.md).

## Important data flow

### Combat schema

`src/sim/search/CombatValueNet.cpp` is the canonical producer:

- `combatFeatureCount()` returns 1,766 state features;
- `combatPolicyFeatureCount()` returns 1,780 total features;
- the final 14 are produced by `combatPolicyFeatureNames` and
  `combatFillActionFeatures`.

State blocks are 26 base scalars, 24 powers, 128 relic flags, four 371-card zone
multisets, 2 enemy aggregates, 45 monster-slot values, 44 potion values, 5
context fields, and 8 relic counters. Policy rows add card/potion/end/select
flags, card properties, target HP, and `Expert` play/obtain values. The archived
v1 schema is retained at `docs/archive/fair-play-dataset-schema-v1.md`, but its
composite-RNG provenance statement is not current truth.

`ScumSearchAgent2` exposes thread-local `g_onCombatDecision`,
`g_onSearchComplete`, and `g_onSearchComplete3` hooks
(`include/sim/search/ScumSearchAgent2.h`). `fairgen` forces the project-fair
Searcher3 regime itself (`search::g_fairPlay` and `search::g_useSearcher3` are
set in its dispatch branch and a message is printed), so its Searcher3 policy
rows are produced even without `STS_FAIR=1 STS_SEARCHER3=1`; the env vars still
gate other modes. `fightgen` installs Searcher2 hooks and omits Searcher3 policy
rows if Searcher3 is forced (`apps/one_combat.cpp::fairGen`,
`runFairGenSeed`, fight-generation callbacks).

### Run/OOC schema

`apps/one_combat.cpp::vFeatCsv` is the rich-state producer and
`v_server.py::RAW` is the implemented 1,017-value consumer layout. Native floor
and win trees select named subsets and map them with `richIdxMap`.
Action-conditioned datasets append screen/action/candidate fields defined by
their specific producer; consumers must use headers, not old comments.

### Grouping and leakage

Correlated samples remain together:

- run values split by seed (`train_winrate.py::GroupShuffleSplit`);
- combat value splits by fight (`train_value_combat.py::group`);
- policy splits by complete decision group (`train_policy.py::group`);
- OOC checkpoint training splits `(seed, decisionIdx)` groups
  (`train_ooc_checkpoint.py::groups`).

Changing a grouping key is a schema/evaluation change and requires documented
leakage analysis.

### Runtime loading

`apps/one_combat.cpp::main` owns environment parsing and load messages. Native
OOC floor/win models are default. Separate combat value, distributional value,
PVNet, and policy models are selected with `STS_VNET`, `STS_DIST_VNET`,
`STS_PVNET`, and `STS_POLICY`. Optional server models are selected through
`v_server.py` environment variables. Current tracked artifact hashes are listed
only in [current baselines](../evaluation/current-baselines.md).
The distributional and PV models are consumed only by Searcher3; a successful
startup load is not evidence of use under default Searcher2.

## Invariants and assumptions

- Feature name, order, normalization, and categorical interpretation are part of
  the model interface, even when column counts do not change.
- Metadata such as seed must not become a learned hidden-RNG feature.
- Training/export/native inference changes require parity on the same trained
  artifact and inputs.
- A successful benchmark requires observable load messages and evidence the
  selected branch used the model.
- File suffix can select serializer behavior; self-play training temporaries
  must preserve the intended XGBoost format (`EXPERIMENTS.md` entry 49).
- Combat policy inputs currently include hand-authored Expert features.

## Known limitations

- No dependency lock or environment definition exists. Scripts import NumPy,
  pandas, XGBoost, scikit-learn, and sometimes PyTorch.
- `parity_test.py` fails loudly when its binary or checkpoint is missing and
  resolves the binary via `STS_PARITY_BIN` or `build/parity_test`, but it does
  not yet load weights into the trained model; real trained-model parity is
  unexercised.
- Searcher3 composite seeding is implemented with explicit per-decision
  `agentSeed`/`decisionIndex` constructor parameters
  (`BattleScumSearcher3::BattleScumSearcher3`); datasets produced before the
  2026-08-02 fix used default-zero values.
- The `fairgen` mode forces the fair Searcher3 regime itself now; datasets
  recorded before that fix may have been produced without it, so historical
  provenance must be read from the archived invocation records.
- `v_server.py` documents the implemented 1,017-value `RAW` layout with
  `apps/one_combat.cpp::vFeatCsv` as the schema owner.
- `OocCheckpointNet::load` does not check every payload read.
- `strategicgen` exists as a data path but no maintained trainer/runtime model
  contract is established for its output. It is experimental.
- Tracked artifacts under `build/` coexist with ignored build output; path
  location does not indicate whether an artifact was generated, deployed, or
  benchmarked.

## Open questions

- Which generated schemas should receive machine-readable version metadata and
  automated producer/consumer checks?
- What parity harness should replace the incomplete distribution-model script?
- How should current artifact versions be named and pinned beyond path names?
- Should strategic generation use explicit structured action fields instead of
  the current screen/action integer pair?

## Relevant code

- `apps/one_combat.cpp::main`, `fairGen`, `fightGen`, `strategicGen`, `vFeatCsv`
- `include/sim/search/ScumSearchAgent2.h` data-generation hooks
- `src/sim/search/CombatValueNet.cpp::combatFeatureNames`,
  `combatExtractFeatures`, `combatFillActionFeatures`
- `train_winrate.py`, `train_value_combat.py`, `train_policy.py`
- `train_combat_pvnet.py::PolicyValueNet`
- `train_ooc_checkpoint.py`; `export_ooc_checkpoint.py`
- `v_server.py::H.handle`, `RAW`
- `selfplay/loop.sh`
- `parity_test.py`; `apps/parity_test.cpp`
