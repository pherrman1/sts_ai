# Combat search

Last verified: 2026-09-24 against current main for the Silver-only dispatch
(ADR-0020), and against the §343 rollout-cost candidate for its scratch-pile
boundary.

## Purpose

This page is the maintained contract for combat state, action enumeration,
search dispatch, hidden information, and leaf guidance on current `main`. It is
not an experiment chronology or benchmark record.

## Current combat dispatch

Silver is the only combat searcher
([ADR-0020](../../../decisions/0020-silver-only-combat-remove-searcher2-and-selfplay.md)).
`one_combat` installs the Silver backend at startup, and every combat goes
through `ScumSearchAgent2::playoutBattle(GameContext&, BattleContext&)`, which
throws when no backend is installed:

1. The backend initializes the `BattleContext` from `GameContext` itself, so
   its observational hooks (for example the Runic-Dome intent observer) see
   initialization. Callers must not pre-initialize the battle.
2. At each decision it converts the visible state into Silver's private
   representation, searches, and resolves the chosen semantic action to a
   live action.
3. The agent validates and commits one live action, then searches again.
4. The loop continues while `bc.outcome == Outcome::UNDECIDED`.
5. `BattleContext::exitBattle` transfers the result and persistent state back
   to `GameContext`. An unresolved combat is a player loss; an enumeration gap
   must never become free progress.

`STS_SILVER_SEARCH=0` and `STS_FAIR=0` make `one_combat` exit with an error.
An explicit sims argument selects flat Silver at that budget in every mode;
only `run`, `bestbench` and `reprobench` called without a sims argument use
adaptive Silver by default (ADR-0018). `BattleScumSearcher3` (ADR-0019) and
`BattleScumSearcher2` (ADR-0020) were removed. The complete flag reference is
[environment-variables.md](../operations/environment-variables.md).

## Silver root-prior tooling

### Offline Silver root mechanism tooling

The user-authorized experimental live root-prior path is separately opt-in via
`STS_SILVER_ROOT_PRIOR_MODEL=<absolute frozen artifact path>`. It evaluates the
frozen `SilverPriorNetV1` at eligible ordinary `PLAYER_NORMAL` roots and passes
native-order aligned priors to the existing root-only PUCT seam (`c=2.5`).
Internal nodes and chance handling remain ordinary Silver search. The bridge
checks the materialized edge fingerprints against the prior surface and fails
closed on mismatch. This path is not the default and its two-seed smoke is not
gameplay-quality evidence; see the [online smoke packet](../../experiments/evidence/silver_prior_online_screen_20260923/README.md).

For the policy-only structured observation/candidate dataset, its reviewed-SHA
collection driver, and training-facing integrity boundary, see
[Silver prior dataset](../operations/silver-prior-dataset.md). That pipeline
uses a separate L/J label entry point and preserves the historical audits.

`STS_SILVER_ROOT_MECHANISM_CAPTURE=<new path>` enables observation-only capture
at the live Silver boundary, after visible-state conversion and before search.
It requires a full `STS_EXECUTABLE_GIT_SHA` and refuses an existing output.
Only nonterminal `PLAYER_NORMAL` roots with at least two legal actions are
emitted. `silver_root_mechanism_v1` records contain the complete visible wire,
semantic actions/native fingerprint order, source SHA, Silver upstream SHA,
source seed, act/floor/encounter, and decision ordinal. The wire contains no
live RNG streams; its isolated search seed is public diagnostic provenance.
Runic Dome and draw-order redaction remain the existing conversion contract.

The root identity is `source_seed/act/floor/encounter/decision`; state integrity
uses a deterministic 64-bit FNV-style checksum of the canonical JSON envelope
(offset 1469598103934665603, multiplier 1099511628211, zero remapped to one).
This checksum is not cryptographic. Artifact byte integrity is SHA-256 in the
selection manifest and must also be recorded for executable/teacher/replay
files in the eventual reviewed run's evidence packet.
`tools/analyze_silver_root_mechanism.py select CAPTURE SELECTED` takes the lowest
64 SHA-256 hashes of UTF-8 root identities, independently of state/labels,
and writes `SELECTED.manifest.json` with capture/selection hashes and IDs.

`silver_leaf_relabel --roots ROOTS OUTPUT SEED EXECUTABLE_SHA` reuses
`relabelOne` for fresh, no-reuse 10k-A and 25k-B searches. Teacher RNG identity
is the same FNV-style hash of `SEED/root_id/A` or `SEED/root_id/B`; collisions
fail closed. The root is its own evaluation reference, so the original-root
victory correction is zero and ordering Q equals the child selection mean.
Every teacher action must have valid Q and match the entire native order.
Scientific mode also requires the root SHA, both teacher record SHAs, both
teacher source-root SHAs, and the CLI SHA to be identical. The optional fixture
budget (32..128) requires exactly one root, marks outputs `fixture_only`, and
cannot supply a scientific replay; it intentionally permits the fixed fixture's
historical source SHA.

`silver_root_mechanism ROOTS LABELS OUTPUT SEED EXECUTABLE_SHA` runs exactly
32 simulations and four common replicates over A native-UCT, B A-Q-order-UCT,
E native-uniform-PUCT, F A-Q-order-uniform-PUCT, C native-visit-PUCT, and D
A-Q-order-visit-PUCT. Ordering is stable descending teacher-A corrected Q, with
native ties. Uniform priors are exactly `1 / legal_action_count`; visit priors
are exactly normalized A edge visits, without smoothing or pruning. Replay RNG
is derived independently as `SEED/replay/root_id/replicate` and checked against
both teachers. Teacher-B judgment uses the maximum B-Q directly, so every
action tied at that maximum is B-best.
`--fixture` requires one root and fixture labels. Scientific mode requires 64.

The dedicated `replaySilverRoot` entry point owns a fresh local session,
validates the complete semantic permutation and finite normalized priors,
and prepares only its root edges. It never changes `SilverSearchConfig` or
exposes gameplay guidance flags. The sole selection change is a default-empty
prior vector checked by root pointer identity: after unvisited-first handling,
root PUCT is `Q_child + 2.5 * P * sqrt(parent_visits) / (edge_visits + 1)`.
Internal UCT, chance DPW, evaluator, and terminal rollout code are unchanged.
Teacher B is used only for regret and best-action judgment; the fixed fixture
test changes B Q and verifies identical treatment actions/priors/order.

`tools/analyze_silver_root_mechanism.py analyze REPLAY OUTPUT` validates the
64×6×4 population, common replicate identities, and per-root replay provenance,
aggregates within root, and reports the eight paired contrasts `E-A`, `C-E`,
`F-B`, `D-F`, `B-A`, `F-E`, `D-C`, and `D-A` with 10,000 root-bootstrap
resamples (Python RNG seed 20260917; empirical sorted endpoints 249 and 9749).
It emits no scientific classification automatically; its predeclared names are
`ROOT_PRIOR_SIGNAL_CONFIRMED`, `ROOT_ORDER_SIGNAL_ONLY`,
`ROOT_COMBINATION_ONLY`, `ROOT_GUIDANCE_SIGNAL_NOT_CONFIRMED`, and
`ROOT_GUIDANCE_INCONCLUSIVE`. Implementation tests
are not evidence of guidance quality; scientific capture/label/replay waits
for independent review and a frozen implementation SHA.

### Removed native searchers

`BattleScumSearcher3`, a particle ISMCTS searcher, was removed with its
particle belief, rejuvenation probes, `STS_S3_*` and `STS_REUSE_*` controls,
and the `fairgen`, `speedtest`, `particle_leaf_probe`,
`particle_posterior_probe`, `fightrep` and `oocv4h1rollout[all]` modes
([ADR-0019](../../../decisions/0019-remove-searcher3.md)).
`BattleScumSearcher2`, the known-RNG/fair-determinization MCTS, was removed
with its rollout, forced-move, live-valid, TT and convergence controls, its
policy-prior/V_combat/PVNet leaf loading, and the `combatgen`, `fightgen`,
`policygen`, `distgen`, `datagen`, `datagen2`, `causalgen` and `searchdiag`
modes (ADR-0020). Their research records remain in the experiment ledger and
[research/](../research/README.md). Reproducing those results needs a binary
built before the respective ADR.

## Hidden information and fair play

`CombatObservation` is the agent-facing public observation. Equality and
`visibleHash` use the same fields, including input state and card-selection
context. Piles compare as multisets of `CardKey`; order-insensitivity is
deliberate. `CombatDistValueNet` takes it as input.

Runic Dome prevents future intent materialization. Looter and Mugger use
`DeferredDirectMoveChoice` for hidden escape-versus-attack continuations.
`assignInformationState` and this deferred choice are project-fair adaptations
of the vendored simulator.

## Silver backend

Silver is an isolated pinned chance-tree backend integrated by
`SilverLiveBackend`; out-of-combat policy stays native. It converts the live
state into a private representation and uses a stable per-battle seed derived
from run/battle identity, not decision ordinal.

Silver retained-search identity ignores historical `curCardQueueItem` at a
quiescent unresolved `PLAYER_NORMAL` or `CARD_SELECT` decision: no action/card
queue entries, no end-turn work, and no battle outcome. It tries ordinary exact
`equalForSearch()` first, then this one-field equivalence. Other search-state
fields stay exact under the existing contract. Pending card-processing states
remain exact even when a selection screen is open; Headbutt's queued
`OnAfterCardUsed` is an example that still needs the active card. The retained
representative and its descendants keep their original queue items during
dedup and reroot. The active root may therefore carry a different historical
item than the observed game while their quiescent search identity agrees.
`queueItemCanonicalHits` counts exact-miss dedup lookups that reused a
historical representative, not unique variants or allocations saved.
Live conversion carries a source-side proof that the queues were empty before
the wire omitted them. Without that proof, including legacy JSON and public
imports, the private search keeps queue-item identity exact for the imported
root and its descendants. Trusted native hard-combat v2 captures persist this
proof separately from the public Silver wire; v1 snapshots remain exact. This
prevents a live `CARD_SELECT` with pending `OnAfterCardUsed` work from being
mistaken for a quiescent selection.

Moving state across the boundary (live-state conversion, private-state
materialization and semantic-action resolution) costs about 10 µs per
decision, under 0.05% of decision time. Root setup (exact reroot or fresh root,
including collection) costs about 2 ms per adaptive decision (2.6%), and search
takes the remainder
([§340](../../experiments/ledger-06.md#340--silver-handoff-timing-and-adaptive-128-seed-baseline-2026-09-24)).
`STS_SILVER_HANDOFF_TIMING=1` reports these buckets per combat.

One private session is retained per battle and exact-child reroot is attempted
after each action. The production cap remains 32,768 nodes. `STS_SILVER_REUSE_CAP=131072`
is an experimental opt-in; it is not a qualified production promotion. The default
`STS_SILVER_REUSE_CAP_MODE=allocated` caps retained allocation; `active` is a
supported opt-in. Reroot and fallback telemetry must state what occurred.

Search nodes contain compact bookkeeping and a pointer to a separately pooled
battle state. Only decision nodes claim state storage; chance nodes have a null
state pointer and read their decision parent's state. Both pools retain stable
object addresses and reuse capacity. Fresh reset resets both active counters;
exact reroot below the configured node cap preserves both pools and the global
dedup table, including currently orphaned transposition statistics. Only when
the old configured cap metric is at or above the cap does the session request
collection around the exact candidate. Collection traverses child edges and
chance-parent dependencies, reclaims unreachable nodes/states (including
inactive high-water slots), and rebuilds retained dedup entries. Retained
addresses, edges, visits and values stay unchanged. The session then rechecks
the cap: a compacted graph below the cap is reused; one at or above falls back.
Thus ordinary below-cap reuse retains baseline policy behavior. Allocated/active
reuse caps count logical
nodes through `allNodes.size()`/`poolUsed`, never state slots or bytes. Pooled
state swaps preserve scratch-buffer capacity reuse. All consumers of these
structures must be rebuilt together after a layout change.

The live adapter matches an immediate observed root against every explored
action edge retained at the prior root, rather than only the selected edge.
This lets any supported listed action inherit the simulations already stored
below its matching successor. It also supports one narrower reroot equivalence
at that boundary. When a retained action and the observed action are
ordinary gameplay-equivalent cards with different UIDs, it swaps exactly
those two UIDs throughout the reachable retained subtree and accepts the
candidate only if the resulting root passes Silver's retained-decision
equivalence check. Hand-order alignment is limited to `PLAYER_NORMAL` roots
without macro continuations. It retargets retained card-edge source indices by
exact card identity and updates each attached chance node's cached stochastic
card action, which later widening replays against the reordered parent hand.
A `CARD_SELECT` root or a root with a continuation cannot be aligned safely
without remapping selection indices and selected bits, so it is not mutated.
This preserves visits for a human-selected equivalent copy without changing
global `equalForSearch()`, action equivalence, or chance-node identity. Any other card-state difference or unsafe queued
intermediate state still takes the ordinary fresh `candidate_missing` fallback.
[ADR-0015](../../../decisions/0015-live-silver-equivalent-copy-reroot.md)
records this boundary.

In the private complete-fight replay, Silver executes its selected action.
For a deterministic selected edge, rerooting therefore verifies the observed
state against that edge's retained decision child. A search-equivalent
`PLAYER_NORMAL` child whose hand has a different internal order is aligned to
the observed order when no macro continuation is present. Root card-edge source
indices and attached chance nodes' cached stochastic card actions are remapped
by exact card identity while visits and descendant states are retained.
`CARD_SELECT` permutations and roots with macro continuations are rejected
without mutation; the private selected-action contract reports a deterministic
state mismatch. Equivalent-copy UID repair uses the same safe alignment.
A selected positive-visit edge without a child fails the replay
invariant. After those repairs, an unexplained mismatch between the selected
deterministic child and the privately executed state fails with a state
diagnostic rather than fresh-rooting. Private sequential card-selection
subdecisions use this same selected-child contract. Quiescent historical
queue-item equivalence applies to deterministic children, sampled chance
outcomes, and live explored-edge matching without rewriting a retained root;
this keeps already-expanded selection descendants internally consistent.
Chance-outcome matching
and the configured reuse cap are unchanged.

At a stable live player-decision boundary, the Java `silverRoot.combat`
projection does not include Silver's native `monsterTurnIdx`. The generic
importer defaults that missing field to the native player-turn sentinel `6`,
while preserving an explicitly supplied value. Defaulting it to `0` would
schedule monster actions immediately after a card play and create spurious
chance branches in the retained search graph.


The live Silver default uses the retained-root adaptive policy: fresh and
one-action/forced roots search 10,000 simulations, while a retained non-forced
root first searches 500, measures the top-two visit-share gap, and stops at 500
when it is at least `0.2932885906040268`; otherwise the same root continues to
10,000 total. `STS_SILVER_ADAPTIVE=0` restores flat Silver. For `run`, `bestbench` and
`reprobench`, an explicit sims argument selects flat Silver at that budget
unless adaptive stopping is configured through its environment variables
([ADR-0018](../../../decisions/0018-silver-default-combat-backend.md)). The policy applies
at ordinary roots and private sequential-selection subdecisions; the first
search is not discarded.

Silver's search-local action enumeration canonically retains the first legal
representative when ordinary playable cards match on all gameplay-relevant
state (`id`, upgrade state, `specialData`, costs, `freeToPlayOnce`, and
`retain`). Different `uniqueId`s remain distinct when either card uses
per-copy special data. The same conservative equivalence is used for the safe
single-card selectors `ARMAMENTS`, `EXHAUST_ONE`, `FORETHOUGHT`, `WARCRY`,
`HEADBUTT`, `EXHUME`, and `LIQUID_MEMORIES_POTION`, after each selector's
eligibility predicate is applied. `GAMBLE` is a separate sequential private
selector: among currently unselected hand cards it retains only the first
representative of each equivalence class, so a class of size `m` still offers
every count from zero through `m`. It does not reorder the hand or rewrite
`selectedBits`. `EXHAUST_MANY` remains physical-index enumeration because its
per-card exhaust processing can affect trigger ordering; it is not covered by
the `GAMBLE` reduction. `DUAL_WIELD`, generated choice lists, draw-pile Secret
Technique/Weapon selectors, and incomplete selection tasks are not collapsed
by this behavior.

The multi-stage retained-root policy was evaluated offline and is not part of
the live runtime. Its analyzer and frozen evidence remain under
`tools/analyze_silver_staged.py` and
`docs/experiments/evidence/silver_staged_grid_2026-09-17/`; production uses the
two-tier 500->10,000 policy above.

Silver exposes sequential selection where live sts_ai exposes atomic
`GAMBLE`/`EXHAUST_MANY` subsets. The bridge executes every private subdecision,
reroots between them, and returns one identity-based atomic subset for live
validation. Conversion and lowering preserve live semantics.

Silver potion legality and root enumeration must stay aligned with the live
action validator. In particular, `GAMBLERS_BREW` is omitted when the live hand
is empty: it would open a `GAMBLE` selector with no legal card selection, so
the live simulator rejects that potion use. For otherwise identical potion
types, Silver retains only the first occupied potion slot as the search-local
representative. It does not reorder or canonicalize the production belt, and
the semantic bridge continues to carry and validate that exact representative
slot. Distinct targeted-potion targets remain separate, and remaining copies
remain available at later decisions after the representative is consumed.

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

Silver dedup uses power-of-two open-addressed storage, starting at 65,536 slots.
A new decision-state insertion that would exceed 50% occupancy doubles capacity
and reinserts existing hash/pointer entries. Duplicate hits never trigger growth.
Node/state addresses, statistics and RNG are untouched; fresh reset clears
occupancy and cap-triggered collection rebuilds retained membership without
shrinking capacity. Fixed widening-cache limits remain independent of dedup.
Frozen whole-combat/OOC teacher protocols and live OOC MCTS require an effective
32,768 cap and reject the experimental 131,072 override before execution.
A larger cap needs separate decision-quality evidence and teacher/model
requalification before promotion.

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

Potion discard remains a legal combat action in `Action::isValidAction`.
Searchers prune discard branches unless discarding a slot leaves another
Entropic Brew available and Sozu is absent; Entropic Brew's modeled effect can
fill each newly freed slot with a generated potion. This includes discard
branches for otherwise usable potions, Fairy in a Bottle, and an unblocked
Smoke Bomb, which also retains its distinct escape action. Alchemize is not
used for this pruning rule because its combat effect is not implemented in the
simulator.

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

At the live semantic boundary, Silver's absent target (`-1`) for an untargeted
card or potion lowers to native target zero. It must never be packed directly
into the unsigned target field: that produces 8191, which is invalid for cards
and denotes discard for potions. Only `discardPotion=true` lowers to native
discard; targeted actions require an explicit in-range target and native
legality validation.

Silver maps native actions into its private model and back using semantic card
and selection identity, not transient position alone. The final lowered action
is revalidated against the live battle.

## Leaf/value guidance

Silver's own leaf evaluation, optional leaf-VNet blend
(`STS_SILVER_VNET_LEAF_*`) and experimental root prior
(`STS_SILVER_ROOT_PRIOR_MODEL`) are described in the Silver backend section.
`one_combat` no longer loads the Searcher2-era compact policy prior, V_combat
leaf, PVNet or DistVNet for play (ADR-0020). The PVNet runtime and the policy
diagnostics were then removed; `CombatValueNet` remains for Silver's leaf blend
and `vnettest`, and `CombatDistValueNet` only for `parity_test`.

Feature ordering and counts are model-interface invariants. Native PV/dist
inference may use probed OpenBLAS or scalar fallback and reports the backend.

## Diagnostics and observability

Closed leaf-evaluation, rollout-trace, frontier/relabel, and sibling-CRN
producers were retired after their research lines closed. The particle and
posterior probes (ADR-0019) and `searchdiag` (ADR-0020) were removed. The
production search path does not depend on a diagnostic callback.

Silver observers are observational unless their flag explicitly names a
treatment. Producers must record fair regime, models and relevant flags so
incompatible rows are not combined.

## Invariants / failure behavior

- Termination is `bc.outcome != Outcome::UNDECIDED`; `isBattleOver()` is
  derived.
- Search mutates copies/determinizations. Only a canonical live-valid action
  may mutate the committed battle.
- The §343 Silver rollout-cost candidate leaves retained tree `CardPile` states
  canonical, while rollout scratch draw/discard/exhaust piles may keep the
  unknown region unordered. Unknown draws remain uniform over the multiset;
  known top and bottom order remains position-sensitive. Rollout scratch must
  never enter a retained node, and diagnostic terminal state is canonicalized
  before bridge serialization. The representation can map a fixed RNG value to
  a different card while preserving the draw distribution; its fixed-work DEV
  quality result is inconclusive and it is not qualified for default
  promotion. See [ledger-06 §343](../../experiments/ledger-06.md) and the
  [evidence packet](../../experiments/evidence/silver_rollout_cost_20260924/README.md).
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
- `include/sim/search/ScumSearchAgent2.h`,
  `src/sim/search/ScumSearchAgent2.cpp`
- `include/sim/search/CombatObservation.h`,
  `src/sim/search/CombatObservation.cpp`
- `include/sim/search/CombatValueNet.h`, `src/sim/search/CombatValueNet.cpp`
- `include/sim/search/SilverLiveBackend.h`,
  `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp`
- `src/sim/search/SilverConversion.cpp`, `apps/one_combat.cpp`

Focused coverage includes `cardselect_parity`, `cardselect_canonical`,
`silver-native-test`, `silver-bridge-test`, `silver-integration-test`,
`runic-dome-lifecycle-test`, `combat-knowledge-neutrality-test`, `vnettest`,
Use current invocation details from
[build-and-debugging.md](../operations/build-and-debugging.md).

## Known limitations

- `CombatObservation` uses `CardKey` multisets and omits some transient card
  fields such as `uniqueId` and retain state.
- Exhaustive ten-card multi-select can create 1,023 subset edges. Pruning and
  canonicalization exist but are policy-affecting opt-ins.
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
