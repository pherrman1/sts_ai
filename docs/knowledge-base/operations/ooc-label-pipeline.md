# OOC label pipeline preparation

Last verified: 2026-10-09 for the outcome-label learning curve (`tools.vwin_outcome_curve`); 2026-10-08 for the CTM escape fit (`ctmescapefeatures`, `tools/ctm_escape.py`); 2026-10-07 for the CTM retrain union, refit flags and declared HP domain, `ctmscorerows` and its model overrides, the learned-stop Python teacher contract, the CTM corpus adapter and `tools.vwin_e1_focal`; 2026-10-06 for the learned-stop `combattransitiongen` teacher; 2026-10-03 for explicit A3 corpus bindings and predictive summaries; 2026-10-02 for A3 sibling ranking and LF native-parity fixtures; 2026-10-01 for A3 offline model tooling, mixed-producer corpus validation, the Violence/Stasis pile-capacity fixes and `vwinrefreshcrashdiag`; 2026-09-30 for Match and Keep policy snapshot isolation; 2026-09-28 for DECISION capture-error continuation; 2026-09-27 for v_win refresh compound capture and the fail-closed `STS_VPATH` guard; 2026-09-26 for local research execution (ADR-0024); 2026-09-11 against the current working tree (RAW transition interfaces).

## Purpose

Prepare a fail-closed, policy-conditioned OOC label workflow. The broad OOC reference teacher is frozen to ordinary project-fair Silver UCT with exactly 10,000 simulations at every private root decision. OOC labels remain expected run-win values; survival/conditional-value decomposition is a representational hypothesis, not a changed objective.

## Boundaries and contracts

The whole-combat input is the canonical 1,766-value rich combat feature vector captured at `decisionIdx=0`, before a committed player action. Labels and diagnostics are read from `GameContext` only after `BattleContext::exitBattle` returns. On victory, `exitBattle` calls `regainControl`, whose normal callback is `GameContext::afterBattle`; the CSV boundary is therefore post-battle/post-`afterBattle` reward-screen entry, not the earlier `g_onBattleExitPersistent` RAW hook. Survival is unaffected. Ending HP includes normal post-combat healing and post-battle effects such as Face of Cleric. Reward generation may already have consumed reward RNG and populated reward state, although reward contents are not emitted. The diagnostic columns do not reconstruct the complete post-battle `GameContext` and must not be treated as a complete transition target. RNG state is neither exposed nor learned, and navigation/act transition remain outside the target.

Every corpus must have an `ooc_pipeline_v1` sidecar validated by `tools/ooc_pipeline_contract.py`. It binds the CSV hash to producer SHA, required executable hash, seeds, timestamp, quarantine accounting, and a combat teacher. A teacher is invalid without a stable identifier, full git SHA, backend/searcher, project-fair regime, exact 10k budget, deterministic/chance exploration 25, widening 3.7028/0.52389, allocated-node reuse cap 32,768, explicit experimental-feature disablement, exact environment, and path/hash for every loaded artifact. Producer and teacher SHA/executable identities must match.

Scientific manifests bind `STS_EXECUTABLE_GIT_SHA` to their frozen SHA. Native
producer and benchmark provenance consumes that declared executable identity
instead of resolving `git rev-parse HEAD` from the launcher's working
directory. Git working-tree variables remain independently relevant to dirty
state and other Git-derived diagnostics.

`wholecombatgen` installs the existing `g_onCombatDecision` observer without changing selection, retains only the first callback, and calls the canonical `combatFeatureRow`. It emits after the existing `BattleContext::exitBattle` call has returned, at reward-screen entry; it does not execute a reward-screen choice. The mode is registered in `tools/seed_guard.sh`; reserve its `.provenance.json` sidecar alongside fresh outputs in the frozen experiment manifest.

#### RAW combat-transition producer

`combattransitiongen` is the first transition-model producer. It follows the
same frozen ordinary project-fair Silver teacher and OOC policy chain as
`wholecombatgen`, but emits JSONL rows through
`apps/one_combat/combat_transition.cpp`. Each row contains the source seed,
fight identity, combat outcome, quarantine status, and a complete
`combat_transition_v1` pre/post persistent-transfer snapshot. The snapshot
covers HP/max HP, gold, terminal potion slots and counts, smoke-bomb state,
stolen gold, ordered relic IDs/counters and bitsets, the full deck including
upgrade/misc/bottle metadata, and all six RNG streams synchronized by
`BattleContext::exitBattle` (`ai`, `cardRandom`, `misc`, `monsterHp`, `potion`,
`shuffle`). Other GameContext fields are copy-through continuation state and
are intentionally not overwritten by `applyCombatTransitionState`.

`combattransitiongen` (not the Lizard candidate mode or other teacher
consumers) also accepts a learned-stop teacher (#418): `search_configuration`
sets `"budget_policy": "learned_stop"` with `learned_stop_model` and
`learned_stop_threshold` equal to the compiled stop model
(`gbt-770201c31f7b`, `0.0323`). The frozen environment then requires
`STS_SILVER_EXACT_ROOT_BUDGETS=0` and `STS_SILVER_LEARNED_STOP=1`, and the
process must run plain learned stopping (no adaptive, searched one-action
roots, boss fallback or boss max). The remaining search constants and the 10,000 cap are unchanged. An absent
`budget_policy` keeps the frozen exact-10k contract, which now also refuses a
process with learned stopping enabled. `one_combat learnedstopteacherselftest`
(CTest `learned_stop_teacher_contract`) checks the loader without running
seeds.

`one_combat ctmscorerows ROWS.jsonl OUT.csv` scores recorded
`combat_transition_row_v2` rows offline with the live OOC MCTS combat stack
(the automatic DeepSets Lizard T2 artifact, Attention V2 Brew fallback and
active-Lizard correction). It parses the row's `predictorInput` and `pre`
state, requires both to round-trip through their serializers, and writes per
row the support reason, `p_death`, expected winning HP and the log probability
of the observed post-combat HP. It runs no seeds (CTest `ctm_offline_score_rows`).
`one_combat ctmscorerows ROWS.jsonl OUT.csv FAST.native STANDARD.native [LIZARD=0|1]`
scores the same rows with another fast/standard pair, such as a research
candidate (default `LIZARD=1`).

The escape capability (#418, see `architecture/out-of-combat.md`) is fitted on
a finished near-full artifact's own HP encoding, so the same steps serve the
Attention and the DeepSets artifacts:
- `one_combat ctmescapefeatures ROWS.jsonl BASE.native OUT` writes `OUT.f32`
  (64 float32 per row) and `OUT.csv` for every surviving row that an
  escape-capable artifact would support. The CSV holds the maxHP and HP labels,
  `escaped`, and `eligible` (not a boss, a Smoke Bomb in a usable slot).
- `tools/ctm_escape.py fit --artifact BASE.native --features OUT --out DIR`
  fits the escape head (L2 logistic regression on eligible TRAIN rows, L2 chosen
  on VALIDATION) and the escape bit on the HP head (zero-column warm start). The
  default `--mode column` fits only the new column, so escape-bit-0 HP stays the
  base head exactly; `--mode head` refits the whole HP head. `fit.json` reports
  escape NLL/Brier against the TRAIN base rate and HP NLL before and after, by
  split. Escapes without an eligible Smoke Bomb (Brew-generated) are counted as
  unrepresentable.
- `tools/ctm_escape.py extend --artifact BASE.native --checkpoint DIR/escape.pt
  --out NEW.native` needs a research-candidate base, writes the escape tensors,
  `capabilities` and the exclusions without `smoke_bomb`.
- `combat_transition_near_full_exposure.py --escape DIR/escape.pt` and
  `NearFullSampler(escape=...)` sample the same factorization in Python (the
  potion trajectory takes `escape=` too), so the Smoke-row relic exposure that
  failed in production can be re-run under it.
- `tools/ctm_capabilities.py writhing-ritual --artifact IN.native --out
  OUT.native` adds the `writhingRitual` capability to a research candidate and
  drops the `writhing_ritual_intersection` exclusion. The exposure script's
  `--writhing-ritual` flag makes the Writhing Mass + Ritual Dagger cohort a
  gated one (it is diagnostic otherwise) and keeps those rows under
  `--final-support`; `--escape` likewise keeps Smoke Bomb rows.
- Escapes with no Smoke Bomb before combat (a Brew-generated Smoke Bomb drunk
  mid-fight) are scored as their own `brewGeneratedEscape` exposure slice,
  always diagnostic-only, and are removed from every gated cohort; the escape
  head conditions only on a Smoke Bomb held at the start. The exact gold
  correction and the near-full export gate only on non-diagnostic slices.
  (Path B run 2: 3 such TEST rows failed the relic slice at +1.15.)
- `one_combat ctmlizardfeatures ROWS.jsonl FAST.native STANDARD.native OUT.csv`
  writes one line per row whose pre-state has an active Lizard Tail: the label
  (0 a win with the Tail unused, 1 a win after it fired, 2 a loss), the routed
  child (standard for Entropic Brew), the Fairy/Brew flags and the child's
  ordinary and reserve survivals. It ignores whether the fast artifact already
  has the Lizard capabilities.
- `tools/ctm_lizard.py fit --features OUT.csv... --out DIR` refits r per child
  on the Tail-fired rows (L2 chosen on VALIDATION) and reports r NLL against the
  TRAIN base rate, q calibration and the three-class NLL by split and cohort
  (plain, fairy, brew). `extend --artifact FAST --fit DIR/fit.json --out NEW
  [--fast-r] [--brew] [--fairy]` writes the capabilities (and the refitted fast
  r) into a candidate fast artifact's header and prints the manifest entries.
  Path B has few Tail-fired rows: about 46 with Brew and 160 with Fairy.
- `tools/ctm_candidate.py` turns the plain exports into a loadable research
  candidate (header-only changes; the payload is copied byte for byte). `stamp
  --artifact STD0 --candidate-id ID --out STD1` declares the standard artifact a
  candidate; the standard capabilities (escape, writhing-ritual) follow on STD1.
  `stamp --artifact FAST0 --control STD --out FAST1` stamps the fast artifact
  (the non-production `package_deepsets_lizard_artifact.py` output) against the
  final standard artifact and rewrites both `controlSha256` fields to its
  SHA256; the fast capabilities and `ctm_lizard extend` follow on FAST1. `manifest
  --standard STD [--fast FAST] --out M.json` writes the `ctm_research_candidate_v3`
  manifest from the headers and prints the two environment variables. Without
  `--fast` it is the interim manifest that `ctmescapefeatures` on STD1 needs; with
  FAST1 it serves `ctmescapefeatures`/`ctmlizardfeatures` on the fast artifact.
  It refuses a pair stamped against a different standard artifact and
  production-promoted inputs; the loader refuses a pair that disagrees on
  `escape`/`writhingRitual` (CTest `ctm_candidate_tool`).
- A retrained standard export loads in C++ only stamped, so native parity
  (`qualify_combat_transition_near_full.py`) and the runtime `support-only`
  probe run on STD1 with the interim manifest's environment variables set (the
  probe subprocess inherits them). When the union TEST split lacks a
  `pre_smoke_bomb_used` row, qualify sets `smokeBombUsed` on an allowed row,
  lists it under `syntheticExclusionFixtures` and requires the native rejection
  reason to name it; `smoke_bomb` and `writhing_ritual_intersection` still need
  real rows.
  `tools/ctm_support_census_check.py --runtime SUPPORT.jsonl --census
  final-support-census-v1.json` checks that the runtime support over the union
  corpus has the census row count, supported count and supported-index digest.

`one_combat combattransitionforcedgen N SIMS ASC OUT SEED TEACHER SETUP`
(#418) runs the same producer and learned-stop-capable teacher contract with
one forced rare state, recorded as `forcedSetup` in the manifest. Its rows are
a separate slice for training and qualification, not ordinary-distribution
rows. Setups:
- `ritual_writhing`: Ritual Dagger is added before the first fight, and every
  act 3 hallway fight becomes Writhing Mass.
- `high_maxhp`: max HP is set to 150..220 at full HP, deterministic per seed.
- `lizard_fairy` and `lizard_brew`: an unused Lizard Tail is added, and while
  it is unused the Fairy Potion or Entropic Brew is refilled before each fight
  when a slot is free.
Mark of the Bloom with an active Tail is already on the exact path, so it has
no setup.

In Python, `validate_teacher` (`tools/ooc_pipeline_contract.py`) treats an
absent or `flat_exact` `budget_policy` as the exact-10k contract, which must
not set `STS_SILVER_LEARNED_STOP`. Like the C++ side, it accepts
`learned_stop` only when the caller opts in with `allow_learned_stop=True`;
only the CTM corpus check (`tools/combat_transition_contract.py`) does, so the
OOC label, v_win refresh, evaluator and Lizard consumers stay exact-only.
`learned_stop` must name its stop model and threshold and set
`STS_SILVER_EXACT_ROOT_BUDGETS=0` and `STS_SILVER_LEARNED_STOP=1`.

`tools/ctm_corpus_adapter.py assemble --index INDEX.json --corpus-root DIR
--scope SETUP --out DIR` turns a corpus generated in many seed units into the
layout `combat_transition_model_experiment.py audit` expects. The index is the
unit-to-file map from the #418 Path B validator. The adapter writes a merged
`corpus.jsonl` plus one shard manifest per unit file under `blocks/`; each is
the unit's own manifest with only `csv.path` rewritten. Seeds the generator
skipped become the merged manifest's `quarantined` list, and one scope
(`forcedSetup`) is assembled per call. `fit --save-test-predictions` writes
per-row TEST predictions (`test_predictions.npz`).
`tools/ctm_survival_compare.py` then compares them with the production stack's
`ctmscorerows` scores on the same rows (`extract-test`, then `compare`, using a
paired source-seed bootstrap).

For the full CTM retrain, `ctm_corpus_adapter.py union --scope-dir SCOPE=DIR
... --out DIR` concatenates assembled scopes, in ascending seed order (by each
scope's seedSpec start, not the `SCOPES` list order), into one
corpus for `combat_transition_surrogate.py prepare`. It drops every row that
the production candidate-contract support predicate rejects (production
`FrozenModels`), and every winning row whose maxHP gain is not one of the
frozen maxHP head's delta classes (`max_hp_delta_domain`; the C++ loader pins
those classes, and Path B has a +14 gain), so later near-full caches keep
`ids == arange(N)`. Its
`row_scopes.json` gives each scope's row range, so main-corpus gates can
exclude forced rows. Two retrain flags reuse production choices instead of
searching again:
- `tools/ctm_hp_domain.py` declares a wider HP domain (`declare --pre-cur-max
  220 --pre-max-max 220` gives classes -219..231, 451 rows) and `expand` widens
  the production HP and relic warm starts to it. Old classes keep their rows. New
  HP-head rows get zero weights and bias -30, and new relic-delta rows copy the
  nearest edge row. The receipt lists the
  `combat_transition_composed.HP_CLASS_RANGE` pin. With `ARTIFACTS` pinned to
  the expanded checkpoints, the support predicate (and so `union`) keeps rows up
  to the declared envelope. The near-full `/160` HP input scale stays fixed.
- `combat_transition_attention_hpo.py --frozen-winner NAME` tunes and refits
  only that candidate;
- `combat_transition_deepset_potion_specialist.py --arms C` refits only the
  warm-started potion-aware control that the DeepSets export consumes. Its
  reproduction check is skipped when `STS_CTM_PINS` sets the reference NLL to
  null. Its decision is `POTION_DEEPSET_CONTROL_REFIT_DONE`; the teacher gate
  is recorded as a diagnostic only, because production W (71d88a71) was
  already `TEACHER_FORCED_REJECTED` on recursive Brew and ships with Brew routed
  to the fallback model, so a rejection is expected and is not a stop.

The retrain chain runs from one pins file that `tools/ctm_retrain_pins.py`
stages. Pinned tools read their keys at import time, so each stage needs every
key, including keys only a later stage determines. `init --domain-dir D`
writes a complete file: the expanded hp/relic warm starts and HP class range,
production placeholders for the rest (listed under `pending`), and null for
the production-cohort count checks a new corpus cannot reproduce
(`gold_evaluate.FROZEN_COUNTS`,
`potion_trajectory_evaluate.PREVIOUS_SUPPORT_ROWS`, the specialist reference
NLL); a null check records the count instead. `init --ascension-center A` (§443, for a
corpus at one other ascension, e.g. A20) sets
`combat_transition_composed.ASCENSION_CENTER`: `FrozenModels` then moves each
warm-start encoder's ascension mean from 0 to A (inverse std stays 1e6), so the
new rows present ascension 0 to the A0-trained weights. Without it, A20 rows
reach those encoders as 2e7 and the FP16 HP encoding is non-finite. Unset or
null (the default, and every A0 run) leaves the checkpoints' buffers unchanged.
The resulting stack is valid only at that ascension. `corpus`, `phase1`, `phase2`,
`near-full` and `hpo` then each derive the keys that stage's outputs
determine, into a new file, in chain order. `union` runs with the `init` pins.
From `phase2` on, the keys `composed_evaluate.verify_data` records must not
change (`check --previous`). `near-full` also derives the DeepSets population
pins (teacher counts, row-id sequences, downstream and recursive-validation
rows). The DeepSets stages follow `hpo`: `control --artifact STD.native`
(the STD export without capabilities), `teachers` (S17), `distill` (S18,
requires `SHARED_TRANSITION_ENCODER_GO`), `downstream` (S19 prepare/fit/compare,
requires `DEEPSET_DOWNSTREAM_GO` for the pinned head unless `--override`
names a `ctm_gate_override_v1` JSON that binds the qualification.json sha256
and its single failure, names the approval and reason, carries the
evidence, and waives only one singleton exact-label accuracy failure; the override
sha256 is recorded in the stage inputs), `potion` (S20),
`specialist` (S21) and `fast --artifact FAST.native`; the last file has an
empty `pending` list. `init` pins `deepset_distill.EXPECTED_CONTROL` to null:
the student is already chosen, so S18 runs without `--control-dir` and
records `control: null`. S17 is `combat_transition_shared_encoder_distill.py
--teachers-only`, which writes only the teacher cache and its receipt. S19
takes `--evidence-from-receipt` (evidence read from the pinned S18
results.json) and `--no-reference-check` (reference downstream metrics are
recorded, not reproduced).
`audit` accepts a union corpus: it validates each scope's own shards (paths
recorded in `row_scopes.json`), takes the completed sources from the union
rows, and quarantines the other sources of the scopes' seed ranges.

The producer's `g_onBattleExitRaw` observer runs after those persistent writes
and before `regainControl`/`afterBattle` for victories, true deaths, and
unresolved exits. It is null by default, composes with an existing observer,
and is restored by `CombatTransitionRawObserverScope`. The native
`combat_transition_oracle` test applies a recorded post snapshot to a detached
copy, invokes native continuation once, and compares complete GameContext/RNG/
reward state with the real exit. This proves the bridge and callback boundary,
not model accuracy or hidden-stream continuation for a learned sampler.

The JSONL output has a hash-bound `<output>.manifest.json`; validate it with
`python3 tools/combat_transition_contract.py <output>.manifest.json`. The
contract requires the full frozen combat teacher, unique `(sourceSeed,
fightIdx)` rows, membership in the declared `seedSpec`, reconciled requested /
completed / quarantined source accounting, six RNG streams, exactly one RAW
capture for a full snapshot, and explicit quarantine reasons. The native
`GameOutcome` value at this RAW boundary is `UNDECIDED` (`1`); the later
victory/loss assignment is deliberately outside the captured observation.

The matching learned-input contract is `combat_predictor_input_v1`, serialized
by `apps/one_combat/combat_predictor_input.{h,cpp}`. It is captured from the
`GameContext` immediately before `BattleContext::init`; the declared encounter
is an explicit exogenous input. Its globals contain character/ascension/act/
floor, HP, gold, encounter, room class, `lastRoom`, potion count/capacity,
`potionKeepValue`, and derived burning-elite presence. Cards are canonicalized
one-token-per-instance with ID, upgrade state, misc, and bottle binding;
relics retain acquisition order and data; all five potion slots retain order.
The input has no run seed, RNG state, hidden encounter queues, true shuffle,
opening hand, monster HP, intents, future rewards, or future map/shop/event
state. Those values remain hidden and are marginalized by the predictor.

Dependency audit classification at this boundary: `BattleContext::init`,
`MonsterGroup::init`/monster construction, `CardManager::init`, and ordered
relic initialization are represented by the included public fields or the
declared encounter (`INCLUDED`/`DERIVED`); monster HP, opening realization,
shuffle, intents, and RNG streams are `HIDDEN_AND_MARGINALIZED`;
Silver backend/search configuration, fixed model artifacts, and fixed search
budgets are `FIXED_BY_TEACHER`; unrelated map/future OOC state is
`IRRELEVANT`. `search::g_potionKeepValue` is the only additional mutable
per-fight policy scalar found and is `INCLUDED`. No material dependency is
`UNRESOLVED`.

`combattransitiongen` keeps the RAW `combat_transition_v1` object unchanged
and emits `combat_transition_row_v2`, adding the matching predictor input.
The manifest binds `combat_predictor_input_v1` and its field-schema hash.
This resolves the input boundary but does not authorize bulk collection,
training, or runtime substitution; collection remains opt-in and
seed-guarded.

Collection remains opt-in and seed-guarded; no runtime adapter or model export
consumes this schema.

Whole-combat training first runs the full corpus validator, including exact canonical feature names/order, exact target/diagnostic suffix, unique fight keys, zero decision index, finite values, and teacher identity. It then uses source-seed groups for train/validation/test, performs variance filtering on TRAIN only, and fits XGBoost survival and winning-only conditional ending-HP models. Its output records the data hash, exact split, retained canonical feature names, parameters, and batch-1 timing. Offline scores do not authorize runtime integration.

`ooccfaudit` is the narrow distribution-shift gate for those frozen models. It reservoir-samples at most one multi-action OOC decision from each source trajectory without consulting sibling outcomes, records the action actually executed by the source policy, copies the same hidden future into every legal sibling, advances each sibling only to its next combat, captures the canonical battle-start vector, and resolves that combat with the frozen teacher. `tools/audit_counterfactual_surrogate.py` is hash-pinned to the Phase-1 models/manifest and reports chosen, unchosen, and combined scoring-rule slices. This audit neither retrains the models nor supplies a complete transition target.

Future branch rows must carry `sourceSeed`, `decisionIdx`, action identity, `futureIdx`, `H`, requested/actual budget schedule, prefix index, survival through prefix, conditional-alive bootstrap value, product, optional dense/reference value, runtime/search cost, validity, quarantine reason, and `teacherId`. Repeated futures and sibling actions are grouped by `(sourceSeed, decisionIdx)` for splitting. The 37 tradeoff contexts remain development/evaluation data and are excluded from training.

Direct-Q and factorized training must consume identical rows, split, representation, and comparable capacity. Survival BCE applies to every valid branch; conditional-value loss only to survived horizons. No placeholder-card sharing or action-subsampling policy is frozen.

## Producer and validation commands

### Semantic action pilot

`oocsemanticcapture` and `oocsemanticeval` provide a separate semantic path;
they do not reinterpret `ooc_pipeline_v1` rows or
`ooc_k_budget_manifest_v1` manifests. The new manifest schema is
`ooc_semantic_manifest_v1`, with row schema `ooc_semantic_action_v1` and
semantic-key schema version 1. The pilot fixes H=1, one future identity and
the existing exact-10k ordinary project-fair Silver teacher. These settings
are a plumbing check, not a scientific choice of eventual H or future count.

Capture reservoir-samples at most one supported, complete, multi-action
semantic decision per source seed without using sibling outcomes. Neow is
excluded. Source trajectories use the existing counterfactual-audit policy.
The primitive observer locates live source states; a deterministic compound's
internally consumed selector is suppressed using the semantic core's own
binding metadata. Library reveals and sequential multi-select picks remain
separate eligible decisions. No semantic branch runs inside that observer.

Capture freezes source metadata and the complete ordered list of canonical
keys, effect/source IDs and lossless typed JSON payloads. Evaluation replays
the source seeds and requires exact equality before evaluating any sibling.
Each sibling starts from a detached copy of the same future, executes via
`executeOocSemanticAction` with the primitive observer detached, and records
the returned `executedPrimitiveBits` as diagnostics only. The established
`finishOocCounterfactual` owns bounded continuation, survival, bootstrap values,
health validation and cost accounting. Its real-combat path uses the
`GameContext` overload so the installed Silver backend owns combat execution.

The semantic validator is `tools/ooc_semantic_pipeline_contract.py`.
It validates typed payload/key identity, exact sibling and future coverage,
teacher and H/budget agreement, provenance and CSV hash binding, raw target
consistency, and simulation accounting including overlapping Silver
transaction decisions. The source representation reuses
`richStateHeader`/`richRow` with the four hidden encounter identity columns
(`nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`) masked to -1.
The ordinary encoder and source/continuation policies are unchanged; this
adapter does not establish complete player-information fairness for the
existing policy stack. Remaining project-fair limitations are recorded in
[determinism and RNG](../behavior/determinism-and-rng.md).

```text
# Run only after implementation verification and executable/teacher freeze.
# TEACHER.json must contain actual matching producer/executable/model hashes.
tools/seed_guard.sh build/linux-gcc-debug-ccache/one_combat oocsemanticcapture 8 SEED_OFFSET MANIFEST.json TEACHER.json
python3 tools/ooc_semantic_pipeline_contract.py check MANIFEST.json
tools/seed_guard.sh build/linux-gcc-debug-ccache/one_combat oocsemanticeval N_DECISIONS MANIFEST.json OUT.csv TEACHER.json
python3 tools/ooc_semantic_pipeline_contract.py validate-corpus OUT.csv.manifest.json
```

The evaluated sidecar binds both the CSV hash and the original capture
manifest hash. Runtime configuration and loaded OOC model identities are
frozen alongside the combat teacher. `richRow` is a quoted CSV cell containing
the masked source vector. The canonical header is stored once in `manifest["stateFeatures"]["header"]`, not
repeated per branch. The validator binds that header to the versioned
`RICH_NAMES` and checks each vector's arity and masked positions against it.
Primitive traces are JSON arrays, while semantic payloads and the requested budget schedule are JSON.
The native `oocsemanticselftest` is a deterministic fixture with a fake combat
backend: it exercises the real branch/continuation call path and observer
lifetime without representing a live Silver pilot.

#### Observational combat-evaluator branch sidecar

`oocsemanticeval N_DECISIONS MANIFEST.json OUT.csv TEACHER.json [COMBAT.csv]`
optionally writes a separate `combat_evaluator_semantic_branch_v1` CSV and
`COMBAT.csv.manifest.json`. Omission preserves semantic-only evaluation.
The sidecar records the existing fight, with no additional Silver simulations:
`vFeatCsv` captures the canonical 1,017 persistent GameContext features before
the backend initializes BattleContext; the shared `combatEvalTerminal` helper
reads the terminal BattleContext before the existing `exitBattle` call.
The combat decision observer composes with and restores any existing observer.
Semantic action execution, continuation, RNG and search accounting are unchanged.

Combat row identity is `(sourceSeed, decisionIdx, semanticKey, futureIdentity,
branchFightIdx)`; semantic action index/source, continuation seed, hidden seed,
encounter and teacher identity are retained. `sourceSeed` is the original
trajectory seed, never a synthetic per-action seed. H=1/futureIdentity=0 emits
zero or one fight per branch; termination before combat produces no fake row.
The combat features use the ordinary unmasked combat-evaluator state contract,
whereas semantic source `richRow` retains its existing four-column mask.

The label helper is shared with `combatevalgen`, preserving V1's HP ratios,
epsilon clamp, validity and quarantine semantics. Wins use terminal player HP
before post-combat healing; true deaths use remaining non-minion enemy HP.
Escapes, turn caps, missing decision hooks and health failures are invalid,
except that a resolved turn-0 terminal during `BattleContext::init` is valid
when the producer has captured the pre-init battle-start features explicitly.
This covers legitimate start-of-combat effects such as Neow's Lament's final
charge without weakening the ordinary missing-hook check.
V1 marks Awakened One true deaths `progressAmbiguous=1` while retaining
`labelValid=1` and a signed target; the existing trainer excludes those deaths
from loss-severity fitting. The sidecar preserves this distinction and does
not make ambiguous death severity suitable for training.

The manifest binds producer SHA, executable SHA256, full teacher, original
semantic capture and evaluated semantic manifest, combat CSV, canonical feature
order, scanned source seeds and outcome counts. Validate it with:

```text
python3 tools/combat_evaluator_semantic_branch_contract.py COMBAT.csv.manifest.json
```

Validation checks the semantic corpus and exact branch provenance as well as
raw feature width/order, finite cells, encounter identity, unique fights,
independently recomputed HP ratios, signed formulas, validity masks and hashes.
The native semantic self-test compares capture off/on at the real branch and
continuation boundary using a deterministic fake backend, including complete
GameContext/RNG fingerprints, primitive traces, health and Silver accounting.
A frozen Release exact-10k paired canary is required before accepting a new
producer. Bulk corpora and canary artifacts belong outside Git; the draft PR
carries temporary verification evidence. This interface does not authorize
training or the larger confirmation cohort before independent implementation
review and merge.

#### Full-run battle-start V_win/L corpus

`combatevalgen` accepts an optional final `RUNOUT.csv` argument. When omitted,
the existing combat-evaluator CSV and behavior are unchanged. When supplied,
the producer writes one source-level terminal row per requested seed, including
`finalOutcome`, `finalWon`, completion/trajectory validity, fight counts,
invalid combat-row counts, teacher identity, and simulator-health/fatal-failure
status. This separates an ordinary invalid immediate label such as an escape
from a trajectory that cannot safely support an eventual-run target.

`tools/battle_start_runout_contract.py` binds the combat CSV and run-out CSV to
the producer/executable hashes, frozen ordinary project-fair Silver teacher,
loaded model hashes, canonical 1,017-feature header/order, exact contiguous
source ranges, and runtime environment. It rejects duplicate or missing source
identities, fatal/incomplete trajectories, non-finite state/labels, impossible
outcomes, mixed teachers, and hash mismatches. V_win eligibility is every row
from a valid completed source trajectory; L eligibility additionally requires
`labelValid && trueDeath && !progressAmbiguous` and retains the existing
`lossRemainingFrac` target. Source-seed grouped split/coverage reporting is
observational only; this producer does not train or deploy either model.

The optional producer is invoked as:

```text
tools/seed_guard.sh build/one_combat combatevalgen N_SEEDS 10000 ASC OUT.csv SEED_OFFSET TEACHER.json RUNOUT.csv
```

The manifest records the effective `runFullRunOOC` policy chain, its runtime
configuration, and every model artifact hash used by that chain in addition to
the Silver combat teacher. A producer must fail closed when either identity
differs. New corrected output uses `dataset_role=primary_corrected_vwin_l`;
the already collected pre-parity raw corpus is retained as explicitly
`dataset_role=heuristic_policy_auxiliary` evidence. It remains usable for
auxiliary LL analysis, but must not be relabeled or pooled as the primary new
V_win/L corpus.

The corpus design uses 128-source shards; larger local collection requires
explicit authorization and the research preflight. This shard size is an
experiment choice, not a repository ceiling. Raw shards, manifests, teacher/model
identities, logs, timings and
coverage reports remain outside Git; semantic-branch, E2/E2c and other
historical corpora are auxiliary evidence and are not silently pooled into
this battle-start corpus.

#### `v_win` refresh and #347 boss-headroom collector

`vwinrefreshgen` extends the same exact-10k native Silver teacher binding and
`runFullRunOOC` continuation loop with outcome-blind semantic sibling capture.
The producer requires Ascension 0, native floor/win models, the V4 token model,
the five V4 strategic gates, the 1.0 strategic margin, keys off, and the other
experimental action/policy overrides off. `loadWholeCombatTeacher` also
requires the teacher's `ooc_policy` and loaded artifact hashes to match the
effective runtime configuration. The V4 token artifact must match pinned
SHA-256 `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.
The frozen-policy guard also rejects enabled `STS_VPATH`/V-informed route
scoring, which is configured separately from the newer path-policy flags and
is not represented by the teacher's effective-policy manifest.

Each source trajectory and each deferred sibling branch writes:

- `MAP`: the 1,017-value `richStateHeader` at every map action, before the
  selected action. The run-out row supplies the eventual `finalWon` label.
- `WIN_RAW`: one victory-boundary row per won fight, captured through the
  composed `g_onBattleExitRaw` observer before `regainControl`/`afterBattle`;
  `postAfterBattleHp` is filled after the ordinary exit call returns. This is
  evaluation/probe data and is not a training target.
  - `decisions`: decision type, complete option keys, chosen option and
    enumeration support/completeness. MAP uses primitive actions; other OOC
    choices use the semantic-action API. Compound selector primitives remain
    part of their parent semantic action; the collector resolves the full chosen
    semantic key from the observed source-plus-selector primitive sequence before
    admitting that decision to the outcome-blind reservoir. On REWARDS screens,
    `CARD_REWARD` covers only card take/skip and Singing Bowl skip choices, with
    siblings limited to the same card-reward group; gold, potion, relic, key, and
    leave actions do not enter this sampling pool.
    Treasure open/leave decisions use a separate `TREASURE` pool, leaving
    `OTHER_SELECTOR` for selectors outside rest/shop parent decisions. Every
    map action is `MAP`, including the singleton row-14 boss link after a rest
    site; singleton decisions are logged but do not enter the reservoir.
- `branches`: one row per sampled sibling, with the chosen option retained and
  at most five other options selected by a deterministic SHA-256 rank when a
  decision has more than six choices. Branches start from detached
  `GameContext`, `PathHistory`, copied agent/RNG and saved OOC thread-local
  policy state, then continue to the end under the same policy chain.

Revision 5 adds the optional `DECISION` capture sink for future screen-aware
value-model work (#379). Set `STS_VWIN_DECISION_SINK=1` when collecting it;
unset or `0` preserves all existing output files and sampling/replay indices.
The sink writes `<PREFIX>.decision.csv` on source trajectories and branches
at each non-map screen with more than one semantic option, including intermediate
shop purchases, reward pickups, and the card selector inside a compound action.
It records the unchanged rich state vector, public screen contents as JSON,
all canonical semantic candidate keys plus the chosen key, and the trajectory's
`finalWon` as `won`. It is capture-only; #334 training still uses MAP rows.

The two decision files serve different purposes: `.decisions.csv` audits
semantic decisions and reservoir eligibility; the optional `.decision.csv`
stores screen-level value-model inputs, including capture-only steps that are
absent from that sampling log.

The CSV prefix is
`sourceSeed,branchId,deviationIdx,rowIdx,decisionIdx,act,floor,screen,teacherId`,
followed by the 1,017 rich features and `screenContents,candidates,won`.
`rowIdx` orders all captured screens within a trajectory. `decisionIdx` joins
an existing sampling decision when present; `-1` identifies capture-only
reward pickups or compound-selector screens. These extra states never consume
sampling indices. `candidates` is a JSON object with `optionKeys`, `chosenKey`,
`supported`, and `complete`. `screenContents` carries a matching screen tag,
public offers/identifiers, and selector or inventory details; it contains no
RNG state or concealed treasure reward. Unsupported/incomplete enumeration or
an unresolved chosen key omits that capture row and records `rowIdx=-1`,
`supported`, `complete`, and `error` in the manifest's per-trajectory capture
log; `enumerationError` preserves the enumerator's diagnostic. Collection
continues with the existing semantic sampling log and replay trace unchanged.
Zero/singleton candidate sets return before chosen-key matching or feature
capture; a partial enumeration is still recorded as an error, since its true
option count is unknown. If a compound choice cannot resolve, its reserved
row is removed and subsequent capture-row indices are compacted.

The optional `decisionSink` manifest section contains a per-trajectory capture
log (including singleton screens omitted from the CSV), row counts by screen
and source/branch, bytes per row, and a linear projection to 4,096 sources.
The validator checks the capture log against the rows, joins sampling decisions
to the existing decision log, and checks JSON/schema, candidate membership,
trajectory labels, counts, hashes, and size reports. Logged capture errors
are counted separately by screen and source/branch in the validator's
`decision_capture_errors` report. An error may not conceal a resolved decision
in the sampling log; unexplained missing rows and invalid captured rows still
fail validation. Older v1 capture logs without error fields remain readable.
Review the measured size before A2; any subsampling rule must be selected and
recorded before collection.

Semantic branches also resume the source policy layer's intra-call continuation.
A card decision observed inside `serverCardRewardPolicy` carries a
`CARD_REWARD_FALLBACK_DRAIN` continuation on its sampled decision; actions
handled by V4 carry `NONE`. After forcing any sibling, remaining card rewards
are drained directly through the same fallback under the decision observer,
before re-entering the outer policy chain. This applies equally to chosen and
untaken siblings and retains intermediate decision/sink rows. The scoped
fallback marker is restored under nesting and exceptions; it is not general
`OocPolicyThreadState`. Normal source fallback gameplay is unchanged.
`vwin_refresh_reward_continuation` exercises a real V4 two-group tie, the
incorrect fresh-entry alternative, all three siblings, and marker lifetime.

`OocPolicyThreadState` also captures the complete Match and Keep preference
cache: seed, act, floor, and `(cardId, upgraded) -> want` entries. Restoring a
sampled branch restores that cache by value before sibling execution, so an
earlier sibling cannot supply preferences computed from another deck or path.
The ordinary seed/act/floor lazy invalidation and within-event preference reuse
are unchanged. `vwin_refresh_match_and_keep_isolation` uses actual hypothetical
card valuation to exercise opposite sibling preferences, nested snapshot
restoration, and multiple clicks in the same event.

For every sampled chosen sibling the producer runs the same forced-action
branch as the counterfactuals. `PARITY_PERCENT=100` checks every chosen replay
on the A1 pilot; `PARITY_PERCENT=5` selects an outcome-independent 5% by the
manifested seed/decision hash for main collection. Parity compares the source
suffix and branch trace, including later semantic decision keys, recorded
combat actions, fight outcomes and terminal/post-afterBattle HP, then checks
the final run result. The old `combatevalgen` output path remains unchanged.
The trace is an OOC/real-combat trajectory trace for this check; the separate
`STS_OOC_MCTS_LEAF_TRACE` MCTS leaf-state probe is deferred until its #363 seam
is available.

Outputs are `<PREFIX>.map.csv`, `.win_raw.csv`, `.decisions.csv`,
`.branches.csv`, `.combat.csv`, `.runout.csv`, and a hash-bound
`.manifest.json`. The manifest binds producer/executable/teacher identities,
effective OOC policy and artifacts, feature-header hash, source seed range,
reservoir/cap/parity rules, the source-seed 70/15/15 split rule, row totals,
chosen-replay parity and output hashes. Its `perType` summary reports decision,
eligibility, support/completeness, candidate-option, sample and branch counts;
branch CPU seconds are reported by decision type and for each branch. Branches
inherit the source seed's split. Validate a completed bundle with:

```text
python3 tools/vwin_refresh_contract.py PREFIX.manifest.json
```

The validator checks each output hash/header, finite numeric fields, seed and
branch joins, one run-out outcome per branch, sampled chosen-option presence,
the six-option cap, the 70/15/15 split metadata, and one `WIN_RAW` row per
victory in each valid trajectory. It recomputes required chosen replays from
the manifested percentage, SHA-256 seed/decision bucket and source validity;
requires PASS for every selected replay; and reconciles runout statuses,
`branchRows[].chosenReplayParity`, branch validity and both parity summaries.
Runout `finalWon` must map victory/loss/unresolved to 1/0/-1. Completion and
trajectory validity must agree with outcome, fatal failure and simulator-health
fields; completed/valid source totals are recomputed from those runouts.
`vwinrefreshselftest` covers option-cap determinism, per-seed reservoir-helper
repeatability, copied agent/RNG and policy state, the rich-feature width and
thread CPU clock. It does not rerun generated trajectories or compare their
non-timing outputs across seeds. `vwinrefreshcompoundselftest` exercises Smith,
Peace Pipe, shop-removal and event compound decisions through selector
resolution, branch execution and chosen-action replay parity. It also runs the
production OOC policy step twice for a real rest-site Smith: the first step
must leave the decision pending on the upgrade selector, and the second must
resolve, sample and replay the full semantic choice. The
`vwin_refresh_rejects_vpath_override` contract test runs with `STS_VPATH=1` and
requires the frozen-policy guard to reject it. `vwinrefreshbranchselftest` is a
single-seed, seed-guarded full-run chosen-branch replay check.
`vwinrefreshdecisionsinkselftest` captures two sequential shop purchases and
leave, verifies reward pickup/card-choice capture and unchanged legacy outputs,
and checks the schema. The compound test also checks the separate selector
row and forced-branch reconstruction. Full two-seed generation compares all
non-timing files with the sink off/on and again with it on:

```text
python3 tools/vwin_refresh_contract.py OFF.manifest.json --compare ON.manifest.json --allow-sink-toggle
python3 tools/vwin_refresh_contract.py ON.manifest.json --compare REPEAT_ON.manifest.json
```

### A3 offline model training and evaluation

`python3 -m tools.vwin_refresh_model` provides four separate stages for #334.
Use the system/repository Python with NumPy, XGBoost and PyTorch installed; the
CPU synthetic tests do not require CUDA. The implementation is offline-only,
does not replace a tracked model, and does not establish gameplay quality.

1. `preflight INDEX --output NEW_REPORT.json` enters through
   `validate_corpus()` and verifies the frozen index identity and exact
   source split (358/77/77 by default). It checks every MAP/runout label join
   and the B0 feature-name contract, and computes variance only on TRAIN MAP rows.
   It produces no model predictions. Strict validation necessarily reads all
   component tables, including TEST metadata/labels; TEST prediction access
   remains closed.
2. `tune INDEX --output NEW_RUN --authorize-full-training [--threads N]`
   performs the later, separately authorized full TRAIN/VALIDATION execution.
   X1/X2 share the 12-recipe CPU-hist grid and selected input features; X2
   constrains only `curHp`. M1 uses TRAIN normalization, the 64/32 GELU network,
   12 recipes, seed-0 tuning and selected-recipe retrains at seeds 0/1/2. The
   lowest validation NLL selects every checkpoint. X1's half-TRAIN check uses
   the lowest hash-ranked half of source seeds under
   `vwin-refresh-334-half-train-v1:{seed}` with unchanged selected parameters
   and early stopping. After selection, the saved checkpoints for all four
   arms execute the shared VALIDATION/TEST resource wrapper on all VALIDATION
   MAP and WIN_RAW rows. `validation-resources.json` records per-arm results,
   timing, cumulative process peak RSS, populations and checkpoint hashes.
   This is execution qualification; resource outcomes do not change model
   selection, and negative quality gates may still qualify execution.
   No TEST feature matrix is loaded.
3. `freeze RUN` binds the selected checkpoints, B0 copy, normalization,
   preflight, validation reports and corpus identity in an exclusive v2
   `freeze.json`. Freeze requires completed selected-checkpoint VALIDATION
   MAP/WIN_RAW resource qualification with matching hashes, full tooling
   identity (Git SHA and files), and numerical runtime. All candidates must
   use the same TRAIN mask.
4. `open-test RUN --confirm OPEN_REAL_TEST_ONCE` verifies the freeze and
   corpus again, including equality of the complete tooling identity and
   Python/NumPy/XGBoost/Torch runtime (CUDA/cuDNN/GPU for CUDA training), then
   consumes an exclusive `test-opened.json` latch before
   reading TEST feature matrices. All four arms use identical metrics,
   source-cluster bootstrap (2,000 replicates), resources and sibling joins.
   A failed evaluation leaves the latch consumed. Recovery requires a
   separately reviewed decision; the CLI never automatically reopens TEST.

Both `preflight` and `tune` accept paired explicit inputs
`--expected-index-sha SHA256 --expected-split-counts TRAIN,VALIDATION,TEST`.
For the final 1,024-source corpus, use SHA-256
`ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00`
and counts `696,155,173`. The CLI requires a 64-hex SHA and exactly three
positive integer counts; neither expectation is inferred from the corpus.
Omitting both flags retains the original 512 SHA and 358/77/77 contract.
The Python `CorpusBinding(index_sha256, split_counts)` copies the named count
mapping into immutable storage. `Dataset` retains its legacy explicit
`expected_sha`/`expected_counts` interface, including empty synthetic splits;
legacy expectations cannot be combined with a binding.

The exact `corpus_binding` is saved in preflight, tuning, VALIDATION resource
qualification, freeze, TEST opening and TEST result records. Qualification,
freeze and verification cross-check the persisted binding and existing SHA/count
fields. TEST opening passes the frozen binding to strict corpus validation.
Missing or inconsistent saved bindings fail closed before corpus access; old
saved runs without bindings must not be silently upgraded or opened. Newly
started 512 runs retain the existing default semantics. The final baseline
feature mask derives from all 696 TRAIN sources; the old scaling experiment's
461-feature mask is not forced, and VALIDATION/TEST variance is never used.

Each overall and breakdown predictive population retains model `nll`, `brier`,
ROC-AUC, ECE and stable equal-mass reliability bins. Descriptive additions are
observed row win rate, a constant predictor equal to that population's row win
rate and its NLL/Brier, plus `outcome_probability_rmse = sqrt(brier)`.
This RMSE is against observed binary outcomes, not an unobserved true state
probability. Unique-source win rate weights each represented source once and
is reported only when labels are constant within every source in that
population; otherwise it is null with an explicit status (also null when source
IDs are unavailable). Constant-baseline NLL uses the same probability clipping
as model NLL, including all-win/all-loss populations. These diagnostics do not
participate in hyperparameter or checkpoint selection.

The reviewed X1/X2 grids and M1 recipes/64-32 GELU architecture remain unchanged.
The categorical encoding and MLP capacity screens are deferred until the final
696/155 baseline rerun makes M1 decision-relevant; they are not unconditional
extensions of `tune`.

Sibling ranking joins `(sourceSeed, branchId)` and scores the first recorded MAP
state after the branch option executes. For `type=MAP`, the producer records
`rowIdx=0` before executing the option, so the evaluator uses the minimum
recorded `rowIdx > 0`. For other decision types it uses the minimum recorded
`rowIdx`, including zero. A branch without an eligible MAP row contributes to
`branches_without_map` and its per-type count, not a ranking pair. Duplicate
row/branch identities and malformed row indices fail closed. Ranking credits
are 1/0 for correct/incorrect outcome ordering and 0.5 for a predicted tie;
95% intervals resample whole source seeds. Native B0 parity fixtures explicitly
use LF line endings for the existing `winnettest` parser.

`qualify-validation RUN` can execute qualification for saved checkpoints when
no successful resource artifact exists. A failed attempt writes a separate
failure report and leaves TEST untouched. The successful artifact is exclusive
and must match the exact checkpoints and tuning manifest being frozen.

`validation-smoke INDEX --output NEW_RUN` exercises all real VALIDATION MAP and
WIN_RAW resource rows without full candidate training. It records a fixed plan
before execution: at most 4,096 TRAIN rows, 1,024 VALIDATION fitting rows, one
XGB recipe per arm with at most 16 rounds, and one MLP recipe with two epochs
per fit and retrain seeds 0/1/2. The feature mask still derives from all TRAIN
MAP rows. These checkpoints and diagnostics carry `purpose=smoke_only` and
cannot be frozen. The eventual selected full-training checkpoints must execute
their own qualification; a smoke artifact cannot substitute for it.

Runtime identity is recorded in tuning, resource qualification, freeze and TEST
results. CPU fingerprinting does not require a GPU; CUDA fingerprints bind the
selected accelerator and deterministic cuBLAS setup. Saved predictors currently
run on CPU. Older freeze records without this binding are rejected. Input
identity changes during tuning or qualification also fail closed.

The compact implementation separates CLI/custody (`vwin_refresh_model.py`),
component-preserving dataset access (`vwin_refresh_dataset.py`), model families
(`vwin_refresh_training.py`) and pure metrics/probes
(`vwin_refresh_evaluation.py`). It writes no numerical cache. Run directories
must be new and must remain local; do not commit datasets or checkpoints.
Preflight binds all component manifests, feature header, split/counts,
TRAIN-selected ordered names/mask, label checks and tooling identity.

B0 uses its serialized feature names. `native_parity()` optionally feeds up to
64 supplied canonical-rich-order rows through an existing `one_combat
winnettest` executable and checks name-aligned Python predictions at 1e-4.
It neither builds C++ nor drives game seeds. Native parity is a separate check
and is not implied by Python tests.

Resource probes retain the terminal-pricing audit conventions: integer HP
sweeps over 1..maxHp, monotonicity tolerance 0.005, flat steps below 1e-6 in the
first ceil(0.6*maxHp) HP, clamped +/-5 local HP slope with denominator 10,
coherent held-potion removal, bounded +/-25 gold, and Feed-like/max-HP-only
changes. WIN_RAW act-boss probes replace HP with `postAfterBattleHp`.
Missing acts/insufficient independent seeds cannot pass the resource gate.
Pre-boss MAP breakdowns derive from recorded act/mapY and the exact native
transition rule: Acts 1-3 at mapY=14 enter the boss at Y=15
(`GameContext::transitionToMapNode`); Act 4 at mapY=2 has the sole boss successor
at Y=3 (`Map::act4Map`). No floor-distance heuristic is used. Sibling scores
join explicit source/branch IDs and take minimum recorded `rowIdx`, counting
branches with no MAP state.

The later offline verdict requires a strictly negative MAP NLL delta CI and
MAP resource qualification; candidates within 0.003 NLL are tied pending
native/in-context speed work. WIN_RAW resource qualification is reported
separately. Neither verdict grants terminal-pricing readiness or promotion.
The tooling PR and synthetic tests are not a full experiment result.

#### Focal retrain and selection gain (E1)

`python3 -m tools.vwin_e1_focal INDEX --x2b-run TUNE_DIR --output NEW_DIR`
retrains the X2-B recipe on the public 457 features as P0 (all MAP rows), F1
(focal rows only: the sibling-ranking join row of each branch, per-decision
balanced weights) and F2 (all rows, focal block upweighted to the non-focal
total), seeds 0/1/2. It reads only TRAIN/VALIDATION components, re-checks
index/manifest/table hashes instead of rerunning the bundle validator, and
requires the frozen X2-B VALIDATION NLL to reproduce exactly. It reports
NLL/Brier on all and focal rows, sibling ranking, and per-type selection gain
(the argmax sibling's branch outcome minus the V4 chosen sibling's) with
source-clustered CIs. Result: ledger-06 §394 (`E1_INCONCLUSIVE`).

#### Outcome-label learning curve (self-play Step 0)

`python3 -m tools.vwin_outcome_curve INDEX E3_ROOT --output NEW_DIR` retrains
the P0 recipe on nested 1/8, 1/4, 1/2, 1/1 fractions of the #334 TRAIN sources,
on source-trajectory rows only (`SRC`, own-play games) and with branch rows
(`ALL`). It scores #334 VALIDATION NLL, selection gain on #334 VALIDATION
siblings and E3 VALIDATION states, the E3 card skip share, and a per-decision
least-squares slope per doubling of games. Result: ledger-06 §415.

### Rich `v_win` information boundary (#397)

`tools/analyze_vwin_public_info_397.py` is the maintained classification of
every `richStateHeader` feature; unknown names fail closed. Only four fields
expose the simulator's realized future queue and are **HIDDEN_FUTURE**:
`nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`. The other four
V4-excluded fields are public: `monOffset`/`eliteOffset` count hallway/elite
combats already entered this act (`GameContext::getMonsterForRoomCreation`,
`getEliteForRoomCreation`; reset at act transition), and `remFights`/
`remElites` are the fixed act queue length (hallway 16/15/15/0, elite
10/10/10/1 for acts 1-4) minus that count. The identity held on every #334
TRAIN/VALIDATION MAP row. `potionChance`, `cardRarityFactor` and `pv*` are
public history; `deckSize`, `potionCount`, `remFights`, `remElites` are
redundant. Relic columns store `1 + counter`; every counter observed in the
#334 corpus is an in-game visible counter.

The public-safe allowlist for future `v_win` training is the TRAIN-variable
mask minus the four HIDDEN_FUTURE fields (457 of the A3 461). Removing them
did not measurably hurt the A3 X1 recipe (ledger-06 §371, `INCONCLUSIVE`
because XGBoost seed noise is ~0.007-0.010 VALIDATION NLL). The tracked B0
`models/v_win_trees.txt` still reads all eight V4-excluded fields. Since ADR-0028 the native
fallback scores 8 public encounter futures by default instead of the realized queue
(`STS_OOC_PUBLIC_FUTURES=0` restores it); on the §422 off base the two settings won 103 vs 104
of 128 paired runs (ledger-06 §434, `LEAK_NOT_SHOWN`).

`tools/analyze_rich_domain_397.py` derives the reachable Ironclad master-deck
card domain from simulator pools and obtain sites (127 of 371 card IDs; 75 red,
39 colorless, 13 curses; Necronomicurse is a literal obtain since #406). The #334 TRAIN variance mask already excludes
every unreachable card, other-class relic and other-class potion column
(ledger-06 §373), so model inputs need no domain filter; the producer keeps the
broad schema. Column index 371 lies beyond the `CardId` enum and is always 0.

Raw public-history families (relics seen but not owned, events seen,
encounters fought), reconstructed from #334 `combat.csv`/`decision.csv` by
`tools/analyze_vwin_history_397.py`, each made a 5-seed X1 ensemble slightly
worse on VALIDATION (ledger-06 §374, preregistered `INCONCLUSIVE`); none is
part of the feature contract. The decision sink leaves 3.2% of event visits
without an `eventId` (first screen single-option or not enumerable).
Rule-derived public probabilities, each checked against the V2.3.4 Java
reference, also gave no held-out gain (ledger-06 §§375–376):
`tools/analyze_vwin_derived_397.py` (potion drop, card rarity, next elite,
next hallway encounter) and `tools/analyze_vwin_derived_rooms_397.py` (?-room
outcome odds, next remove price). Adding a monotone duplicate of
`potionChance` alone moved the 5-seed X1 ensemble by +0.0056 NLL, so feature
changes below about ±0.005 are not resolvable on the #334 TRAIN/VALIDATION
split. The derived-feature code is the reference if a later value model wants
these public quantities.
With the A3 M1 MLP instead of XGBoost (ledger-06 §378,
`tools/analyze_vwin_mlp_397.py`) no family qualified either; relics seen but
not owned improved every MLP seed but the gain came from a few sources, and
the MLP stays well behind the XGBoost baseline.
#396 Stage 1 (ledger-06 §418, `tools/analyze_vwin_map_396.py`) ablated the
12-field forward-map block (`fmD*`, `fmC*`, `curMapX/Y`) and, separately,
`bossId` from the public-safe set: both `INCONCLUSIVE` (map removal +0.0050
NLL [−0.0012, +0.0109], every seed worse; retraining null +0.0026). Both stay
in the contract; richer map encodings are not justified by #334 evidence.

### Mixed-producer v_win refresh corpus

`tools/vwin_refresh_corpus.py` validates a read-only index of existing producer
bundles. It calls the unchanged `validate_bundle()` for every component, then
requires complete, valid source trajectories and an exact, globally unique
source-seed cohort. It never generates data, concatenates tables, rewrites
bundles or presents multiple producers as one. An incomplete full cohort must
fail; validating an explicitly declared subset establishes only that subset.

The `vwin_refresh_corpus_v1` JSON index has exactly four fields:

- `schemaVersion`: `"vwin_refresh_corpus_v1"`.
- `sourceSeeds`: a nonempty array of distinct, nonnegative integer source seeds
  (expand any intended range explicitly).
- `allowedProducers`: a nonempty array of objects with `producerGitSha`,
  `producerExecutableSha256`, `teacherManifestSha256`, `teacherId` and
  `teacherManifest` (path to the original, hash-bound teacher JSON). These four
  identity fields form one allowed tuple, preventing arbitrary recombination.
- `components`: a nonempty array of `{ "manifest": "old/seed.manifest.json",
  "sha256": "<manifest SHA-256>" }` objects.

All index paths resolve relative to the index file; absolute paths also work.
Each table is found beside its own component manifest using the existing bundle
suffix contract. The producer's recorded `teacherPath` is retained as historical
provenance, while the index's hash-checked `teacherManifest` path locates the
teacher. Thus an evidence directory can move without editing old manifests.

The teacher file must equal the embedded `combatTeacher`, and `policy` must
equal its `ooc_policy`. The existing OOC teacher validator enforces native Silver
and exact10k search configuration; the corpus also requires project-fair RNG
and binds teacher ID, Git SHA, executable SHA and
`environment.STS_EXECUTABLE_GIT_SHA` to the explicitly allowed identity.
Only after those checks are the four teacher binding fields removed for
semantic comparison. These are the exact differences observed between the old
and repaired #334 recovery freezes. All other teacher fields, including full
environment, model paths/hashes and OOC flags/parameters, must match, even in
allowed producers with no components yet. No wildcard normalization is exposed.

Component comparison retains feature schema/header/hash, split, sampling/K/cap,
parity rule/rate, Ascension, DECISION configuration/label/encoding/join semantics,
all table headers (including the combat target suffix) and unknown manifest
metadata. Only producer/teacher identity/path fields, output hashes and known
per-bundle observations (`integrity`, `perType`, `branchRows`, seed start/count,
parity checks/failures and DECISION row/size/trajectory measurements) are excluded.
The existing bundle schema defines MAP labels through runout `finalWon` and
keeps `WIN_RAW` diagnostic-only; the corpus introduces no new training targets.
Missing sampling, teacher or policy specifications fail closed.

```python
from tools.vwin_refresh_corpus import validate_corpus

corpus = validate_corpus("evidence/corpus.json")
for table in corpus.tables("map.csv"):
    # Carry this component alongside any loaded rows and branch identifiers.
    source_manifest = table.component.manifest_path
    producer = table.component.producer
    csv_path, csv_sha256 = table.path, table.sha256
```

`corpus.manifests()` enumerates resolved manifest paths; `corpus.components`
retains manifest hashes, original producer identities, teacher paths/hashes,
source seeds and table hashes. `tables()` yields existing paths with their
component attached and skips an optional table absent from the corpus. Keep
artifacts immutable during consumption: validation is a snapshot, not a file
lock. Revalidate after changing any input.

```text
python3 tools/vwin_refresh_corpus.py evidence/corpus.json
python3 -m unittest tools.test_vwin_refresh_corpus tools.test_vwin_refresh_contract -q
```

Synthetic tests cover mixed identities, different directories, relocation,
cohort failures, strict component rejection, provenance hashes, semantic
mismatches and the limited teacher-binding normalization. CTest registers
`vwin_refresh_corpus_selftest` as `core;tooling`. This API does not modify frozen
external analysis/training scripts; those consumers must explicitly adopt it
and retain component provenance. Passing this validator establishes artifact
integrity and compatibility, not gameplay quality, salvage safety or permission
to continue generation.

### Producer diagnostics and generation

`vwinrefreshcrashdiag 1 OUT_PREFIX SEED TEACHER.json MAX_BRANCHES MARKERS.log`
is a diagnostic-only, seed-guarded variant of `vwinrefreshgen` for one source
seed: it keeps the production teacher/policy guard, exact 10k, K=1, the
six-option cap and branch order, stops after `MAX_BRANCHES` sibling branches,
writes no manifest, and appends flushed `<branchId> <phase>` markers around
`runCombatEvalGenSeed`, the collector/runout writers, branch bookkeeping and
branch-local destruction. Production `vwinrefreshgen` writes no markers.

`ActData_ViolenceAction` (Violence) used a 64-entry stack `fixed_list` for draw
pile attack indices, while `CardPile` is unbounded; a native Silver rollout that
grew the draw pile past 64 attacks overflowed it (A2a seed 13001491, Golden Idol
branch `s13001491-d6-e4060641b190`). The Bronze Orb Stasis helper
(`MonsterSpecific.cpp`) had the same 64-entry pattern over the cards of one
rarity in the draw or discard pile. Both temporary lists are now `std::vector`
with unchanged ordering, card choice and RNG use (the `int` casts keep the
32-bit `Random::random` overload); `unit-test violence_large_draw_pile` and
`unit-test stasis_large_pile` pin pre-fix digests and cover more than 64
candidates. In a locally rebuilt pre-fix GCC 13 `-O3 -flto` release frame, the
65th Violence entry lands in an unused 4-byte slot (same result as an unbounded
list) and later entries reach the stack canary, so such a process fails stop
unless the overwrite happens to reproduce the canary value. That frame layout is
a property of the compiled binary: data from a pre-fix producer stays held out
until the frozen producer itself is inspected.

`one_combat vwinrefreshpolicyspec POLICY.json` exports the effective loaded
OOC policy without generating trajectories. Use it for the teacher's
`ooc_policy`, with that executable's hash and source SHA; the producer still
checks all teacher fields and loaded artifacts before generation.

The A1 command uses 128 sources from 13,000,000, K=1, exact 10k and 100% chosen
replay checks. It is run only after the implementation review and frozen SHA:

```text
STS_VWIN_DECISION_SINK=1 tools/seed_guard.sh build/linux-gcc-release/one_combat vwinrefreshgen 128 10000 0 PREFIX 13000000 TEACHER.json 1 100
python3 tools/vwin_refresh_contract.py PREFIX.manifest.json
```

`bossheadroom347gen` uses the same fixed 128-source cohort. It retains valid
boss-entry states by act (11/11/10, or all available below quota), ranked by
`sha256("boss-headroom-347-v1:{seed}:{fightIdx}")`. Arm A replays exact 10k and
must match the source outcome and terminal HP; only then are B100 (flat 100k)
and B30 (flat 30k) valid paired comparisons. The mode writes source states,
per-arm outcome/signed-outcome/HP/first-action/CPU/simulation/decision rows and
a provenance manifest. `tools/analyze_boss_headroom_347.py` requires the
adjacent hash-bound manifest and verifies the state/arm joins before analysis.
Both bundle loading and the analysis entry point require source-state rows,
recompute A's outcome/terminal-HP match, and reject contradictory match flags.
A valid B100 or B30 arm requires a matching valid A replay; quarantined A states
are excluded from both paired analyses.
It reports paired metrics and source-seed-clustered bootstrap intervals
overall, by act, and by boss; applies the Stage-1 classification thresholds;
and flags the authorized extension case.

The analysis command is:

```text
python3 tools/analyze_boss_headroom_347.py PREFIX.arms.csv
```

`bossheadroom347gen` reconstructs sources through `runCombatEvalGenSeed`, whose
non-combat step is `runFullRunOocPolicyStep` only: it never runs live OOC MCTS,
so it cannot reproduce an MCTS-policy source even when `STS_OOC_MCTS=1`.
`bossrescue347 1 SELECTION.json STATE_ID OUT_PREFIX` (research-only, one source
per process) instead calls the ordinary `runFullRunOOC` under the source arm's
environment. A thread-local `t_bossEntryHook` (`run_driver.h`, unset elsewhere)
captures the selected act's boss entry before Silver initializes the battle and
records that fight's action trace. The mode requires the reconstructed run to
match its historical `bestbench` row, replays the entry with the original
planner seed (control parity: outcome, terminal HP, full trace, post-exit state
digest), then with fresh planner seeds at two flat exact budgets. Fresh planner
seeds use the thread-local `g_nativeSilverPlannerSeedOverride`, which replaces
the game seed in each Silver search root (search RNG streams and rollouts) and
leaves the live battle untouched. Native Silver's `NativeSilverCombatStats` now
also counts search steps per searched root, so a replay can prove its budget.
`bossrescue347selftest 1 SEED SIMS` checks the replay boundary on one act-1
boss. See the [#347 rescue pilot packet](../../experiments/evidence/boss_budget_rescue_347_pilot_20261007/PLAN.md).
A second selection schema, `boss_preparation_rmatch_347_selection_v1`, lets a
source declare `expectedSourceWon` (0 or 1, so a won boss fight can be a
source), replays `plannerReps` fresh flat-10k planner seeds keyed by
`boss-prep-347-planner-v1:{runSeed}:{act}:{rep}` (shared by every source of a
run seed), and writes a descriptive `entryDescriptor` (HP, gold, potions, deck,
upgrades, relics, RNG stream counters, `PathHistory.roomVisits`). The #425
schema is unchanged and refuses `expectedSourceWon`. See the
[#347 boss-preparation packet](../../experiments/evidence/boss_preparation_rmatch_347_20261007/PLAN.md).
A third schema, `boss_deaths_default_347_selection_v1` (§417), replays
default-stack boss deaths: it requires source arm `default`, plain learned-stop
Silver (no boss fallback, boss max at most 10k), OOC MCTS off and no
`expectedSourceWon` (the source fight must be lost). It replays `plannerReps`
fresh planner seeds keyed by `boss-deaths-347-planner-v1:{runSeed}:{act}:{rep}`
under that same learned-stop policy; the budget check is that every searched
root used at most 10,000 steps. See the
[#347 boss-deaths packet](../../experiments/evidence/boss_deaths_default_347_20261009/PLAN.md).
Research-only `STS_OOC_DECISION_TRACE=<path>` (diagnostic build `1ed47e5c`,
on the #428 build `5549a16a`) makes `runFullRunOOC` append one JSON line per
real out-of-combat step (state before and after, what a reward, shop or boss
relic screen offered, and whether OOC MCTS, the Match and Keep step or the
ordinary chain decided) and per battle. It only reads state; with it set, the
eight #428 sources reproduced their frozen rows exactly. `STS_RUN_PROFILE`
already records each OOC MCTS root's prior, visits and Q. See the
[#347 OOC divergence packet](../../experiments/evidence/ooc_divergence_347_20261007/README.md).

No pilot or Stage-1 cohort is part of implementation verification. The default
4,096-seed A2 collection still requires explicit authorization; no training,
model export, leaf-runtime routing, Silver terminal pricing or gameplay/default
promotion is performed by these producers.

#### Fresh confirmation orchestration and offline analysis

`tools/run_ooc_semantic_confirmation.py` is a deliberately fixed experiment
runner for seeds 992000 through 993023: 64 independent shards, each retaining
the native 16-source command ceiling. It can run locally when explicitly
authorized and preserves completed, validated shards. `freeze`, `capture`, `gate`
and `evaluate` are separate stages. Evaluation requires every capture to
validate, an explicit hash-bound capture-distribution review, and frozen
analysis script hashes. The source archive, pinned dependencies, Release
executable, teacher and model hashes are fixed before capture. A user-local
GNU `time` provides per-process CPU and memory accounting; worker processes use
`OMP_NUM_THREADS=1`. Capture/evaluation stage timing includes source/replay work,
whereas semantic CSV timing and simulation totals describe branch work only.

The runner requires each successful or resumed evaluation bundle to match its
expected capture path/hash, seed block, producer, executable and teacher.
Failed or unrecorded outputs require inspection; they are not silently
rerun or overwritten. Source/model/executable provenance remains distinct from
the orchestration and analysis tool hashes. An archive build must identify its
producer explicitly with `STS_EXECUTABLE_GIT_SHA`; an enclosing checkout's SHA
is not the archive producer.

`tools/analyze_ooc_semantic_confirmation.py` validates the complete fresh corpus
and reuses the development probe's unchanged state/action encoders, fixed
160-tree depth-3 XGBoost configuration and deterministic five-fold grouping.
It uses decision-centered qProduct targets and 5,000 paired decision bootstrap
replicates. All seven source families and compound-containing/non-compound
slices keep complete sibling groups. The state-only pairwise null is 0.5;
its selected-action metrics depend on row order and do not imply ranking skill.
The report separates the handoff's point-estimate/interval eligibility from
judgments about meaningful harm and family/fold concentration; it does not
invent an unstated equivalence margin. No development decisions are pooled
into the confirmation result and no production model is exported.

`tools/analyze_semantic_combat_labels.py` validates all combat sidecars and
reports coverage, label distributions, missing-combat branches and the unchanged
`train_combat_evaluator.py::stable_split` source-seed partitions. Its inherited
30 nonambiguous held-out-death screen is a coverage heuristic, not a statistical
power calculation: correlated sibling deaths are not independent samples.
The command never fits a combat predictor. Full capture/evaluation timing can
be supplied separately as combined runner metadata. Large CSVs and raw logs
remain external evidence; compact results belong in the experiment ledger.

The native modes and seed guard enforce a 16-source pilot ceiling. Increase
scanning beyond eight sources only when needed for structural examples; this
interface does not authorize corpus scaling or training. An absent or stale
local frozen teacher blocks the live pilot: synthetic checks may verify the
interfaces, but cannot authorize later corpus generation. Acceptance also
requires inspection of complete raw decision groups, distributions, traces,
costs and zero unexplained health/quarantine or replay failures.

```text
python tools/ooc_pipeline_contract.py check build/ooc/whole_combat.manifest.json

tools/seed_guard.sh build/one_combat wholecombatgen N_SEEDS SIMS ASC build/ooc/whole_combat.csv SEED_OFFSET build/ooc/teacher.json

python tools/ooc_pipeline_contract.py make-manifest --teacher build/ooc/teacher.json --csv build/ooc/whole_combat.csv --output build/ooc/whole_combat.manifest.json --producer-sha PRODUCER_SHA --executable-sha256 EXECUTABLE_SHA256 --seed-spec "{\"start\":SEED_OFFSET,\"count\":N_SEEDS}" --requested N_SEEDS --completed COMPLETED --quarantined QUARANTINED --rows ROWS

python tools/ooc_pipeline_contract.py validate-corpus build/ooc/whole_combat.manifest.json

STS_XGB_DEVICE=cpu python tools/train_whole_combat_surrogate.py build/ooc/whole_combat.manifest.json build/ooc/surrogate

python tools/ooc_pipeline_contract.py budgets 1000
python tools/ooc_pipeline_contract.py budgets 1000,1000
python tools/ooc_pipeline_contract.py budgets 1000,1000,1000
python tools/ooc_pipeline_contract.py budgets 500,500
python tools/ooc_pipeline_contract.py budgets 333,333,334
python tools/ooc_pipeline_contract.py budgets 150,100,50

python tools/ooc_pipeline_contract.py h-plan TOTAL_BRANCHES --futures 1,2,4

python tools/make_ooc_k_budget_manifest.py PR100_AUDIT.csv build/ooc_k_budget/manifest.json

python tools/freeze_ooc_k_budget_experiment.py --manifest build/ooc_k_budget/manifest.json --executable build/one_combat --model floor=models/v_rich_trees.txt --model win=models/v_win_trees.txt --output build/ooc_k_budget/experiment.json

tools/seed_guard.sh build/one_combat oockbudgeteval 32 build/ooc_k_budget/manifest.json preflight.csv 10000,10000,10000 0 0 A build/ooc_k_budget/experiment.json -1 24

tools/seed_guard.sh build/one_combat oockbudgeteval 32 build/ooc_k_budget/manifest.json stageA_A.shard-00-of-24.csv 10000,10000,10000 4 0 A build/ooc_k_budget/experiment.json 0 24

tools/seed_guard.sh build/one_combat oockbudgeteval 32 build/ooc_k_budget/manifest.json stageA_B.shard-00-of-24.csv 10000 4 100 B build/ooc_k_budget/experiment.json 0 24

# Launch one command of each arm per index 0..23 (with concurrency within the authorized local resource budget),
# substituting the same zero-padded index in the filename and numeric argument.
python tools/analyze_ooc_k_budget.py stageA_A.shard-*-of-24.csv stageA_B.shard-*-of-24.csv --spec build/ooc_k_budget/experiment.json --output analysis.json
```

`oockbudgeteval` consumes an `ooc_k_budget_manifest_v1` JSON manifest frozen by
`tools/make_ooc_k_budget_manifest.py` from the complete PR-100 audit CSV. Before
opening an output, it replays every source decision under the exact-10k Silver
source policy and requires a one-to-one match for every frozen action bit plus
semantic description and for the complete legal sibling set. It refuses a
non-fair, non-Silver, non-exact-budget, non-allocated-32768, or adaptive
environment.

For A futures, `finishOocCounterfactual` exposes const observational callbacks
after each completed fight's normal OOC continuation reaches the next battle.
The callback bootstraps a detached copy through the existing `vStateRaw` and
`vStateWin` contract, so checkpoint calculation cannot consume the continuing
branch's RNG. The same branch continues to terminal. Optional
`STS_OOC_K_CHECKPOINT_EQUIV=1` reruns the identical continuation without the
callback and fails unless terminal outcomes and search counts are identical.
B futures emit terminal truth only. A/B future identities are explicit and
`tools/analyze_ooc_k_budget.py` rejects overlap, incomplete coverage, invalid
rows, duplicates, or mismatched action coverage before source-seed-clustered
analysis. The evaluator writes to an exclusive `.partial` path and renames it
only after every branch succeeds.

Checkpoint bootstrap validity mirrors `finishOocCounterfactual`: initialize
from the current discrete floor and zero run-win value, then accept each model
estimate independently only when finite and within its established domain. In
particular, a finite floor estimate slightly below the already-reached integer
floor falls back to that integer floor; it does not invalidate an otherwise
finite run-win target. Simulator-health failures still invalidate the complete
branch.

Expensive K-budget arms use the frozen 24-process source-seed modulo sharding
recorded in the experiment spec. Pass `SHARD_INDEX SHARD_COUNT` after the spec
argument (indices `0..23`, count `24`). Each output filename must end in its
`.shard-II-of-24.csv` assignment, and an atomic `.claim` directory prevents
duplicate processes from racing on one partial output. The zero-future atomic replay uses shard index `-1` with
count `24`. Analyze all 24 completed CSVs together; exact cohort checks fail
closed if any source-seed shard is absent. Process sharding is used because
simulator globals make in-process threading unsafe.

Failure recovery may use the separately frozen 12-way
`(actionIdx, futureIdentity)` modulo partition within one source shard. Pass
`WORK_INDEX WORK_COUNT` after the source-shard arguments (indices `0..11`,
count `12`) and bind both assignments in the output filename. Every worker
still replays the complete frozen decision and sibling set before evaluating
only its assigned branches. Merged analysis remains fail closed on duplicates
or incomplete action/future coverage. When a decision has fewer than three
actions, `4 * actionCount` is less than 12 and some valid workers intentionally
produce a header-only CSV; those files are still part of the complete recovery
worker set.

If and only if Stage A authorizes Stage B, launch the same 24 indices with A
future start `10` for each frozen schedule (`10000`; `5000,5000`;
`3333,3333,3334`; `150,100,50`) and distinct schedule-prefixed shard files.
Analyze those 96 files together with the unchanged 24 Stage-A A files and 24
Stage-A B reference files.

### Counterfactual OOC labels (`ooccfpilotgen`)

`one_combat ooccfpilotgen N_SEEDS OUT_PREFIX SEED_OFFSET TEACHER.json FUTURES
[STATES_PER_SEED] [CARD_BOSSES] [GEN] [TYPES] [TARGET.json|-] [FUTURE_START]`
(`apps/one_combat/combat_datasets.cpp::oocCounterfactualPilotGen`). It is
seed-guarded, and the launcher is
`docs/experiments/evidence/ooc_cf_pilot_20261007/run_corpus.sh`. The source
run and the per-type reservoir are those of `vwinrefreshgen` with K=1. Each
retained option of a selected CARD_REWARD, BOSS_RELIC, REST or SHOP decision
is forced FUTURES times. Run k of every sibling redraws the hidden future
(`sampleNoncombatFuture`) from `sha256(...:{seed}:{decisionIdx}:{k})`, so all
siblings share common random numbers.

- **GEN=1 (pilot, default):**
  - The future is redrawn after the forced option.
  - The horizon is the first boss fight after the branch, or the second for
    card rewards when CARD_BOSSES=2. The label is HP after that boss.
  - The cap is #334's: the chosen option plus five, hash-ranked.
- **GEN=2:**
  - The future is redrawn *before* the forced option, so randomness the option
    itself consumes is sampled too. The generator fails closed if the redraw
    changes the published screen or any rich field other than the four
    HIDDEN_FUTURE fields (#397).
  - Every branch plays to the end of the run. The label is `finalWon`;
    first-boss win and HP after it are diagnostics.
  - `.options.csv` holds the rich row right after the option at the first
    requested k (zero by default).
    `.map.csv` holds one rich row per run at the first MAP screen after the
    branch screen is finished. The map row can differ across k after a boss
    relic, because the next act's map is generated from the redrawn future.
  - The option cap first merges keys that differ only in `occurrence=`
    (identical cards at other deck positions). It always keeps the chosen
    option and the skip/leave options, then fills up to six by
    `sha256(ooc-cf-option-cap-v2:...)`.
  - States are drawn only from TYPES (comma list), ranked by
    `sha256(ooc-cf-pilot-v2-select:{seed}:{type})`.
  - The manifest counts selected states by type and act.

GEN2 accepts a nonnegative `FUTURE_START` (default zero), with each actual
future index `k=FUTURE_START+j` recorded in the existing SHA256 domain and
output rows. The start plus count must fit an integer. Use `-` for an absent
target file when supplying only the start. Omission of both new arguments
preserves the existing state reservoir, six-option cap and future identities.
The native producer accepts the frozen exact-root teacher or an explicitly
validated learned-stop teacher; its nominal simulation count of 10,000 is a
cap, not an override forcing learned-stop roots to exact 10k. Source and
continuation share that configured teacher. Bind the effective policy and
verify actual search usage in the experiment receipt; other producers and
Python corpus validators retain their own teacher support boundaries.

#### Targeted REST diagnostics

Targeted GEN2 REST preflight and future ranges verified on 2026-10-08.

`TARGET.json` is opt-in producer instrumentation, limited to GEN2,
`N_SEEDS=1`, `STATES_PER_SEED=1` and `TYPES=REST`. Schema
`ooc_cf_target_v1` requires `sourceSeed`, `act`, `floor`, `screen` equal to
`REST`, and an `optionKeys` array. The target selects the initial campfire
screen before reservoir sampling, not its following upgrade/removal selector.
No matching root, repeated matching roots or an invalid source trajectory
fails closed.

A target with `FUTURES=0` performs one complete, seed-guarded source run and
no continuations. Its `.target.json` receipt records the exact observer
`decisionIdx`, public-state SHA256, actual chosen semantic key, full legal
keys, retained keys and producer/binary/teacher/effective-policy binding.
The public fingerprint masks all eight legacy encounter-queue fields and
adds the visible deck metadata, relic counters, potion slots, map and screen
contents. Empty `optionKeys` inventories every legal key in this preflight;
optional expected decision and public hash can additionally constrain it.
This preflight still has source execution cost and is not a no-seed check.

Positive futures require the preflight's `decisionIdx` and
`publicStateSha256`, its `preflightReceiptPath` and SHA256 in
`preflightReceiptSha256`, plus explicit nonempty `optionKeys`. Receipt schema,
preflight status, file hash and producer/binary/teacher/effective-policy
binding must match before replay. The replayed root identity, public hash and
actual baseline key must match before any continuation. The captured baseline
is always retained alongside every requested legal key; this targeted set
bypasses the ordinary six-option cap. Duplicate or unknown requested keys are
errors. The receipt and manifest bind the exact retained set and k range.

Freeze named alternatives before their labels, and preregister disjoint
selection and evaluation future ranges. Repeated futures are a paired local
counterfactual diagnostic at one source state, not independent source runs
or population win-rate evidence. `vwinrefreshselftest` (CTest
`vwin_refresh_producer_contract`) covers parsing, binding requirements,
selection, hidden-invariant public fingerprints and ordinary cap behavior;
actual target replay fidelity still needs a frozen guarded preflight/canary.

### E3 corpus analysis

`python3 -m tools.vwin_e3_cf ROOT --output NEW_DIR [--corpus334 INDEX]` analyzes
GEN=2 outputs. It verifies part manifests and hashes, masks the four
HIDDEN_FUTURE fields for X2-B and drops them for retrained arms, and drops any
(state, k) group with an invalid sibling. The split is `source_split`, and
TEST is scored only with `--open-test`. It reports per-state selection gain
against V4's choice and map-row NLL/Brier. Arms: X2B, an E3-only GBM with a
learning curve, and, with the local #334 index, F2_334 and F2. Result: ledger-06
§396.

## Schema examples

```text
sourceSeed,fightIdx,act,floor,encounter,roomClass,decisionIdx,teacherId,<1766 canonical features>,won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac,startPotionIds,endPotionIds,startPotionCount,endPotionCount,goldDelta,smokeBombUsed,changedRelicCounters,ritualDaggerChanges,deckStructureChanged,parasiteAdded,persistentMutationSummary

sourceSeed,decisionIdx,actionBits,futureIdx,H,budgetSchedule,prefixFight,budgetSpent,survivedPrefix,conditionalAliveValue,qProduct,denseReferenceValue,runtimeMs,valid,quarantineReason,teacherId,<shared state/action features>
```

## Decision gate and eventual order

Proceed only if survival clearly beats the constant baseline, calibration is reasonable, conditional ending HP substantially beats its conditional mean, and batch-1 inference is negligible versus search. Even then, do not integrate it. Phase 2 must test persistent/RNG transition effects and downstream OOC-label bias.

1. Finish and independently validate combat work.
2. Choose/freeze a strong reference combat teacher.
3. Record teacher SHA/config/model hashes.
4. Generate a small fresh transition pilot.
5. Train/evaluate survival plus conditional HP.
6. Decide whether Phase 2 is worthwhile.
7. Run compatible K/search-budget diagnostics.
8. Choose K/search schedule.
9. Run fixed-compute H=1/2/4.
10. Choose H.
11. Preregister issue-#19 pilot conditions.
12. Generate/inspect a small clean OOC pilot.
13. Generate a large replacement corpus only if healthy.
14. Train matched direct-Q/factorized models.
15. Compare held-out ranking/calibration.
16. Run mandatory paired online/fair evaluation.
17. Promote only with clean provenance and at least equivalent online strength, preferably improvement.

Old terminal outcomes are not truth for a materially changed teacher.

## Known limitations and deferred work

- The scientific run supplies the exact frozen producer SHA, server-built executable hash, and loaded-artifact hashes after the implementation commit.
- The semantic pilot supports only H=1 and one future; multi-H semantic
  experiments and replacement corpus generation remain separate work.
- Trainer act/room/encounter slices use a configurable minimum population
  (`--minimum-slice`, default 20); the pilot should preregister any override.
- No runtime integration, scientific seeds, GCP work, real-data training, OOC regeneration, K/H experiment, or gameplay benchmark was run.
