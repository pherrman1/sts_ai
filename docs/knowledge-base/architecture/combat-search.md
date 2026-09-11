# Combat search

Last verified: 2026-09-10 against the current working tree.

## Purpose

This page is the maintained contract for combat state, action enumeration,
search dispatch, hidden information, and leaf guidance on current `main`. It is
not an experiment chronology or benchmark record.

## Current combat dispatch

`ScumSearchAgent2` owns combat policy dispatch for `one_combat`:

1. `BattleContext::init` copies persistent run state from `GameContext` and
   initializes combat-only state.
2. `playoutBattle` uses known simulator RNG. `playoutBattleFair` constructs a
   project-fair search from information available at the current decision.
3. Search operates on copied or determinized battles and must not mutate the
   live committed `BattleContext`.
4. The selected root action is validated and executed on the live battle.
   Fair play commits one action before observing and searching again.
5. The loop continues while `bc.outcome == Outcome::UNDECIDED`.
6. `BattleContext::exitBattle` transfers the result and persistent state back
   to `GameContext`. An unresolved combat is a player loss; an enumeration gap
   must never become free progress.

Default combat is known-RNG `BattleScumSearcher2`. `STS_FAIR=1` independently
selects project-fair dispatch, and `STS_SEARCHER3=1` selects
`BattleScumSearcher3`. `STS_SILVER_SEARCH=1` installs Silver and overrides the
native searcher choice. The complete flag and parameter reference is
[environment-variables.md](../operations/environment-variables.md).

## Searcher2 / Searcher3

### Searcher2

`BattleScumSearcher2` is the default MCTS implementation. Normal dispatch
searches copied battles with their existing simulator RNG, so it is a known-RNG
policy. Its tree is retained across decisions when the committed action can be
advanced into the existing root.

Searcher2 can also run through fair dispatch. Its determinization resamples
draw order and the shuffle/card-random streams, but not all six combat RNG
streams. This is a supported compatibility path, not the complete project-fair
hidden-state model.

Searcher2 uses UCB-style selection without learned priors and PUCT when a
compact policy model or enabled PVNet policy head provides priors. A loaded
PVNet contributes policy only; PVNet value blending is Searcher3-only.

### Searcher3

`BattleScumSearcher3` is particle ISMCTS. Its tree is action-keyed and each
simulation samples a `HiddenBattleState` particle with replacement. Particles
carry draw order and all six combat RNG seed pairs and counters. The tree may
be rerooted after a committed action and is reseeded per real decision.
Fair dispatch constructs a fresh native searcher at every live decision;
non-fair dispatch can carry and reroot the tree.

The composite search seed uses visible-state hash, agent seed, and decision
index. Increasing `STS_S3_PARTICLES` (default 64) increases belief construction
and filtering work; it does not make each simulation replay every particle.

At a node Searcher3 enumerates actions for the current determinization,
computes optional priors, selects and executes an edge on a copy, then descends,
expands, directly evaluates, or rolls out. Conservative dead-state pruning
applies only where the player cannot act. Chain compression and forced-action
contraction reduce work without changing the committed legal action.

Fair+Searcher3 enables live-valid stored-edge selection by default. It
re-scores only stored edges legal in the current particle with the same
UCB/PUCT rule; if none is legal, search uses its configured fallback.
`STS_LIVE_VALID=0` disables it. Forced-action contraction is enabled for fair
dispatch by default and `STS_FORCED_MOVE=0` disables it.

### Supported non-default search controls

| Area | Current contract |
| --- | --- |
| Reuse and allocation | Native trees reroot when possible. Searcher3 exposes reuse limits/diagnostics, carried-tree Q selection (`STS_REUSE_ALWAYS_Q`), and fresh-tree Q selection (`STS_S3_ALWAYS_Q`). |
| Stable-root budgeting | `STS_CONV_ROOT` grows root search until its visit-share/value stability rule or budget limit. It owns its forced-move pool behavior. |
| S3 toggles | `STS_S3_BELIEF`, `STS_S3_PRUNE`, `STS_S3_CHAIN`, and `STS_S3_LIVE` default on. Pool redirect, root CRN, semantic card edges, and union expansion are opt-in. |
| Invalid-edge fallback | `STS_S3_EXPAND` adds missing live legal edges when no stored edge is valid; its max and simple-selection controls remain supported. |
| Rollouts | `STS_ROLLOUT_DEPTH` caps actions. S3 also supports prior-guided sampling, K-rollout averaging, turn-stop bootstrap, tactical turn-beam rollout, and rollout-length VNet alpha. Defaults are heuristic rollout, one sample, no turn stop, and no cap. |
| Chance continuations | `STS_S3_PERSISTENT_ENDTURN_CHANCE` stores exact-`CombatObservation` successor nodes below eligible END_TURN edges while retaining one aggregate action value/visit stream. It samples one normal transition per simulation and is incompatible with strategy-fusion diagnostics and eager END_TURN marginalization. |

Research treatment parameters are summarized here, not recommended. Exact
defaults, compatibility rules, and output paths live in the environment
variable reference.

## Hidden information and fair play

`CombatObservation` is Searcher3's public information-state identity. Equality
and `visibleHash` use the same fields, including input state and card-selection
context. Piles compare as multisets of `CardKey`; order-insensitivity is
deliberate. The action-keyed tree shares action statistics across compatible
hidden worlds rather than branching the whole tree by observation.

`Belief::initial` creates particles and `Belief::sampleIndex` samples normalized
weights. `applyParticle` installs hidden draw order only when pile size and card
multiset still match; stale incompatible order falls back to searcher-RNG
shuffle.

Conditioning has two distinct paths:

- Historical in-search `Belief::update` compares particle draw order with a
  visible pile prefix. Hypothetical internal updates are off by default, so a
  simulation does not condition the root belief on its own observations.
- `STS_S3_REAL_BELIEF_FILTER=1` is the exact real-boundary filter. For each
  particle it restores the pre-action state, applies the particle, executes the
  committed action canonically, and compares predicted and real post-action
  observations. Compatible particles retain equal normalized weight;
  propagation failures are reported. Zero survivors restore a uniform prior.
  `STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1` instead rebuilds from current reality.
  Neither path is rejuvenation.

`STS_S3_PERSIST_FILTERED_BELIEF` transfers the filtered posterior to a fresh
next-decision tree. Shadow sensitivity, rejuvenation, RNG-exposure, and belief
audit modes observe this machinery without defining the default policy.

Runic Dome prevents future intent materialization. Looter and Mugger use
`DeferredDirectMoveChoice` for hidden escape-versus-attack continuations.
`assignInformationState` and this deferred choice are project-fair adaptations
of the vendored simulator.

## Silver backend

Silver is an isolated pinned chance-tree backend integrated by
`SilverLiveBackend`; out-of-combat policy stays native. It converts the live
state into a private representation and uses a stable per-battle seed derived
from run/battle identity, not decision ordinal.

One private session is retained per battle and exact-child reroot is attempted
after each action. The production cap is 32,768 nodes. The default
`STS_SILVER_REUSE_CAP_MODE=allocated` caps retained allocation; `active` is a
supported opt-in. Reroot and fallback telemetry must state what occurred.

Search nodes contain compact bookkeeping and a pointer to a separately pooled
battle state. Only decision nodes claim state storage; chance nodes have a null
state pointer and read their decision parent's state. Both pools retain stable
object addresses and reuse capacity. Fresh reset resets both active counters;
reroot retains both pools. The allocated/active reuse caps still count logical
nodes through `allNodes.size()`/`poolUsed`, never state slots or bytes. Pooled
state swaps preserve scratch-buffer capacity reuse. All consumers of these
structures must be rebuilt together after a layout change.


`STS_SILVER_ADAPTIVE=1` searches 1,000 simulations, measures the top-two
visit-share gap, and, when below threshold, continues the same root to exactly
3,700 total. It applies at ordinary roots and private sequential-selection
subdecisions; the first search is not discarded.

Silver exposes sequential selection where live sts_ai exposes atomic
`GAMBLE`/`EXHAUST_MANY` subsets. The bridge executes every private subdecision,
reroots between them, and returns one identity-based atomic subset for live
validation. Conversion and lowering preserve live semantics.

Silver potion legality and root enumeration must stay aligned with the live
action validator. In particular, `GAMBLERS_BREW` is omitted when the live hand
is empty: it would open a `GAMBLE` selector with no legal card selection, so
the live simulator rejects that potion use.

The default-off leaf observer runs where Silver would start `SimpleAgent`. It
can receive a versioned wire snapshot and root/parent/leaf identity, project it
into a live `BattleContext`, and call the existing `CombatValueNet::predict`.
Terminal states retain exact evaluation. Shadow evaluation, corpus/relabeling,
and sticky-quality sampling are diagnostic producers unless a direct callback
is explicitly enabled.

Bridge conversion, lowering, transaction, and validation failures are
fail-closed and must never commit an invalid live action.

Silver player statuses use a sorted sparse vector (`PlayerStatusMap`) with
signed 16-bit values and explicit membership independent of zero. Wire order,
first-insertion-wins semantics, and equality remain unchanged. Insertion
invalidates references and iterators; current status-processing loops queue
actions or change existing entries/status bits without inserting during iteration.
The native simulator retains its own status representation.

Silver caches the diagnostic root hash lazily only when a leaf observer needs
it, invalidating on fresh reset and reroot. Rollout timing starts only for an
observer requesting a result. Action counts remain exact with the default-off
`BattleSearcher::recordActionTrace`; enable it before searching to retain the
full `printSearchStack` action sequence. The observer's action counts and
fingerprints do not depend on that debug vector.

Chance widening memoizes the original floating-point expression for visit
counts below 32,768, with independent END_TURN/general parameter caches and
exact-formula fallback above that range. Parameter changes invalidate the
corresponding schedule. This cache limit does not change the widening limit or
allocated-node reuse cap. UCB scanning stops only when the current best score
is positive infinity, retaining the original first-winner tie behavior.


## Action enumeration / semantic bridge

`search::Action::execute` and `isValidAction` define execution and legality.
Both native searchers use `Action::enumerateCardSelectActions`, including the
correct pool per task, EXHUME self-exclusion, CODEX skip, and all valid subsets
for `EXHAUST_MANY` and `GAMBLE`.

`STS_MULTISELECT_MODE=all|single|none` controls subsets. `all` is default and
the complete validity contract; `single` keeps empty, singleton, and full
selections; `none` keeps only empty. `STS_MULTISELECT_CANONICAL=1` optionally
collapses masks selecting the same multiset of effect-equivalent hand cards.
Identity includes id, upgrade, turn cost, free-to-play state, and special data,
so materially distinct copies remain distinct.

Learned action features append eight subset-content fields after the original
fourteen. Older compact models consume their declared count and PVNet consumes
the original fourteen. Two fields come from `ExpertKnowledge` play/obtain
weights, so learned policy intentionally includes hand-authored guidance.

Silver maps native actions into its private model and back using semantic card
and selection identity, not transient position alone. The final lowered action
is revalidated against the live battle.

## Leaf/value guidance

Without a learned leaf, search uses exact terminal values and rollout-based
non-terminal estimates. A compact policy supplies priors; `STS_CPUCT` controls
PUCT exploration when learned priors are active.

Except in `policygen`, an unset `STS_POLICY` attempts to load
`models/policy_trees_c.txt`; `STS_POLICY=0` disables it and an explicit path
overrides it. An explicit load failure is reported.

Fair+Searcher3 auto-loads `models/v_combat_7k_tuned.txt` with blend weight 0.3
when `STS_VNET` is unset. Explicit `STS_VNET` overrides it; load failure reports
and disables the model. Searcher2 and non-fair paths do not auto-enable it.

Supported value mechanisms:

- `STS_VNET`/`STS_VNET_ALPHA`; boss/Act-3 conditions and rollout-length alpha
  are opt-in.
- `STS_VNET_PER_ENCOUNTER` loads an all-or-nothing encounter-model directory,
  with optional `_pooled.txt` fallback. In-file `combat_mlp_meta_v1` deltas use
  the same encounter dispatch.
- `STS_VNET_RANK_CORR` and `STS_VNET_RESIDUAL` load default-off additive
  corrections; missing/invalid artifacts leave them off.
- `STS_DIST_VNET` is Searcher3-only.
- `STS_PVNET` provides joint policy/value. Its enabled policy head takes
  precedence over compact policy. Searcher3 can blend value; Searcher2 uses
  policy only. `STS_PVNET_VALUE_ONLY=1` makes it inert in Searcher2 and does not
  activate zero-prior PUCT in Searcher3.

The Searcher3 PVNet visible-state cache defaults on when PVNet is loaded and
`STS_PVNET_CACHE=0` disables it. Keys are the fresh `visibleHash` of the state
actually evaluated. Turn/depth/boss gates affect per-expansion blend only, not
direct or post-rollout evaluation.

Feature ordering and counts are model-interface invariants. Native PV/dist
inference may use probed OpenBLAS or scalar fallback and reports the backend.

## Diagnostics and observability

Closed leaf-evaluation, rollout-trace, frontier/relabel, and sibling-CRN
producers were retired after their research lines closed. The retained
particle/posterior probe implementation lives in
`apps/one_combat/particle_diagnostics.{h,cpp}`. `S3LeafDiagnostic` and
`g_onS3LeafQuery` remain Searcher3 interfaces for those probes; the production
search path does not depend on a diagnostic callback.

`SearchDiagnostics` records simulation partitioning, rollout entry/stop causes,
tree actions, maximum depth, and search time. Per search:

```text
simulations = terminalInsideTree + rolloutCalls + leafDirectEval
rolloutCalls = rolloutLeafCalls + fairIllegalStoredEdge
```

`searchdiag` emits decision rows for both searchers. Searcher2 can also emit
independent staged-budget probes; Searcher3 emits agent rows only. Fight
summaries have a separate schema. `collectFrontierStats` classifies terminal
and unexpanded leaves with a bounded walk.

Belief/root/reuse telemetry, END_TURN diagnostics, retained particle probes,
and Silver observers are observational unless their flag explicitly names a
treatment. Producers must record fair regime, models, particles, and relevant
flags so incompatible rows are not combined.

## Invariants / failure behavior

- Termination is `bc.outcome != Outcome::UNDECIDED`; `isBattleOver()` is
  derived.
- Search mutates copies/determinizations. Only a canonical live-valid action
  may mutate the committed battle.
- Unresolved exit, empty action set, invalid edge, bridge failure, or model-load
  failure takes an explicit defensive path; it must not award progress, reuse
  stale state, or claim a model loaded.
- Terminal nodes are not expanded. Fair re-expansion clears stale terminal
  state when another determinization is non-terminal.
- Node/edge/searcher layout, action features, observation identity, wire
  versions, and model feature counts are interfaces. Rebuild all including
  translation units after C++ layout changes.
- Observation equality and `visibleHash` retain one field contract. Persistent
  chance children use exact equality, not diagnostic hash, as identity.
- Fair search does not reveal hidden choices before the committing action.
  Search and diagnostics do not consume gameplay RNG merely to sample or log.
- Death pruning stays conservative until sound for every input state.
- Artifacts are active only after successful load; file presence proves
  nothing about use.
- Multi-select `all` remains the complete legal-action contract. Pruning modes
  are explicit policy-affecting opt-ins.

## Relevant tests and code

Primary code:

- `include/combat/BattleContext.h`, `src/combat/BattleContext.cpp`
- `include/sim/search/Action.h`, `src/sim/search/Action.cpp`
- `include/sim/search/BattleScumSearcher2.h`,
  `src/sim/search/BattleScumSearcher2.cpp`
- `include/sim/search/BattleScumSearcher3.h`,
  `src/sim/search/BattleScumSearcher3.cpp`
- `include/sim/search/ScumSearchAgent2.h`,
  `src/sim/search/ScumSearchAgent2.cpp`
- `include/sim/search/CombatObservation.h`,
  `src/sim/search/CombatObservation.cpp`
- `include/sim/search/CombatValueNet.h`, `src/sim/search/CombatValueNet.cpp`
- `include/sim/search/CombatPVNet.h`, `src/sim/search/CombatPVNet.cpp`
- `include/sim/search/SilverLiveBackend.h`,
  `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp`
- `src/sim/search/SilverConversion.cpp`, `apps/one_combat.cpp`

Focused coverage includes `cardselect_parity`, `cardselect_canonical`,
`scum_nonfair_empty_edges`, `scum_convroot_stale_outcome`,
`silver-native-test`, `silver-bridge-test`, `silver-integration-test`,
`runic-dome-lifecycle-test`, `combat-knowledge-neutrality-test`, `vnettest`,
and `pvnetparity`. Use current invocation details from
[build-and-debugging.md](../operations/build-and-debugging.md).

## Known limitations

- Searcher2 fair determinization does not cover the full hidden RNG state.
- Searcher3 shares an action-keyed tree across particles. A stored edge can be
  illegal in one world; live-valid selection and explicit fallback handle it.
- `CombatObservation` uses `CardKey` multisets and omits some transient card
  fields such as `uniqueId` and retain state.
- Exhaustive ten-card multi-select can create 1,023 subset edges. Pruning and
  canonicalization exist but are policy-affecting opt-ins.
- Exact real-boundary filtering and posterior transfer are opt-in; the default
  belief path is not an exact posterior across every committed action.
- Terminal run-value guidance depends on its evaluator's feature coverage and
  never substitutes for exact terminal combat utility.
- Retained research controls are supported and testable, not thereby promoted.

## Evidence routing

Current configuration and performance belong in
[current-baselines.md](../evaluation/current-baselines.md). Active, parked, and
closed research belongs in [current-research.md](../evaluation/current-research.md)
and [research/](../research/README.md). Chronological evidence is indexed by
[EXPERIMENTS.md](../../../EXPERIMENTS.md) and stored in
`docs/experiments/ledger-*.md`.

Use those sources for benchmark numbers, rejected variants, promotion
decisions, and implementation history. Keep this page limited to the current
architecture and behavior contract.
