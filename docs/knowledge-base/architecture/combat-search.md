# Combat search

Last verified: 2026-10-06 for #367 v_win terminal pricing (default off); 2026-09-25 for native-only Silver (ADR-0022), the native default
(ADR-0021) and Silver-only dispatch (ADR-0020).

## Purpose

This page is the maintained contract for combat state, action enumeration,
search dispatch, hidden information, and leaf guidance on current `main`. It is
not an experiment chronology or benchmark record.

## Current combat dispatch

Silver is the only combat searcher
([ADR-0020](../../../decisions/0020-silver-only-combat-remove-searcher2-and-selfplay.md)),
and it runs natively on the main engine
([ADR-0021](../../../decisions/0021-native-silver-default.md),
[ADR-0022](../../../decisions/0022-remove-vendored-silver.md)).
`one_combat` installs `NativeSilverBackend` at startup, and every combat goes
through `ScumSearchAgent2::playoutBattle(GameContext&, BattleContext&)`, which
throws when no backend is installed:

1. The backend initializes the `BattleContext` from `GameContext` itself, so
   its observational hooks (for example the Runic-Dome intent observer) see
   initialization. Callers must not pre-initialize the battle.
2. At each decision it builds the search root from the visible state (below),
   searches, and maps the chosen root action onto the live battle.
3. The agent validates and commits one live action, then searches again.
4. The loop continues while `bc.outcome == Outcome::UNDECIDED`.
5. `BattleContext::exitBattle` transfers the result and persistent state back
   to `GameContext`. An unresolved combat is a player loss; an enumeration gap
   must never become free progress.

`STS_SILVER_SEARCH=0`, `STS_FAIR=0` and `STS_NATIVE_SILVER=0` make `one_combat`
exit with an error, as does any `STS_SILVER_*` option the native backend does
not honor (the vendored model's options; see
[environment-variables.md](../operations/environment-variables.md)). An
explicit sims argument selects flat Silver at that budget in every mode; only
`run`, `bestbench` and `reprobench` called without a sims argument use a
budget policy by default: learned stopping (ADR-0026, which replaced the #199
adaptive default of ADR-0018). `STS_SILVER_ADAPTIVE=1` selects #199.

### Removed searchers and tooling

`BattleScumSearcher3`, a particle ISMCTS searcher, was removed with its
particle belief, rejuvenation probes, `STS_S3_*` and `STS_REUSE_*` controls,
and the `fairgen`, `speedtest`, `particle_leaf_probe`,
`particle_posterior_probe`, `fightrep` and `oocv4h1rollout[all]` modes
([ADR-0019](../../../decisions/0019-remove-searcher3.md)).
`BattleScumSearcher2`, the known-RNG/fair-determinization MCTS, was removed
with its rollout, forced-move, live-valid, TT and convergence controls, its
policy-prior/V_combat/PVNet leaf loading, and the `combatgen`, `fightgen`,
`policygen`, `distgen`, `datagen`, `datagen2`, `causalgen` and `searchdiag`
modes (ADR-0020).

The vendored Silver model (`third_party/silver_lightspeed`, its bridge and
`SilverLiveBackend`) was removed with every research tool that needed it
(ADR-0022): Silver telemetry and handoff timing, scaling/budget/sequential/
sticky-quality/root diagnostics, hard-combat and root-mechanism captures and
replays, leaf-VNet blending and the leaf corpus, the learned root prior
(`SilverPriorNetV1`) with its dataset, training and screening tools, the
tactical-prefix, first-action, forced-action and rollout-variance studies,
the reuse-cap and exact-visit-lock/rho-racing stopping controls, and the §349
rollout scratch-pile option. Their records remain in the experiment ledger and
[research/](../research/README.md); reproducing them needs a binary built
before the respective ADR.

## Hidden information and fair play

`CombatObservation` is the agent-facing public observation. Equality and
`visibleHash` use the same fields, including input state and card-selection
context. Piles compare as multisets of `CardKey`; order-insensitivity is
deliberate. `CombatDistValueNet` takes it as input.

The search never sees the live RNG streams, draw order the player cannot see,
or intents hidden by Runic Dome; the next section says how the root is built.
The combat knowledge tracker (`CombatKnowledgeState`) is the only source of
positional draw-pile facts and of public pre-roll monster state.

## Native Silver search

`SilverSearcher` (`src/sim/search/SilverSearcher.cpp`) is a port of the Silver
fork's `BattleSearcher` production path on the main `BattleContext`, installed
by `NativeSilverBackend`. At each decision the backend copies the live state,
turns the draw pile into the player's information set from the knowledge
tracker (known bottom, unknown multiset, known top; concrete under Frozen
Eye), and reseeds all six RNG streams from a public per-battle seed
(`nativeSilverBattleSeed`) so no live randomness reaches the search. The search
treats the six streams as one chance source (`SearchRng.h`): an action that
advances any stream becomes a chance node whose outcomes reseed every stream
from `base + N`. Transpositions use `BattleContext::equalForSearch`/
`hashBattleState`; `equalForSearch` ignores the last played card at a quiet
decision and compares hand, and (with an information-set draw pile) discard
and exhaust, as multisets.

The backend reroots onto the dedup node equal to the new live view when one
exists, compacting unreachable nodes at the 32,768-node cap, and maps the
chosen root action to the live state by card identity
(`SilverSearcher::translateAction`, which falls back to a search-equivalent
copy). When no node matches exactly, `findNodeUpToEquivalentCopy` retries with
the unique ids of one pair of search-equivalent cards exchanged, so playing a
different physical copy than the one the search expanded (the root
deduplicates equivalent copies) still reuses that branch (ADR-0023). The
exchange is only a lookup: `equalForSearch` and the dedup table stay exact,
and cards whose special data matters (Ritual Dagger, Genetic Algorithm) are
never exchanged. A root with exactly one legal action
(for example a forced End Turn or a one-option selection) is committed without
search; the retained graph is kept, so the next decision can still reroot
through it. `STS_SILVER_SEARCH_SINGLETON_ROOTS=1` and exact root budgets
restore searching such roots. Other roots search a flat
`simulationCountBase` (x `bossSimulationMultiplier` in boss fights unless
`STS_SILVER_EXACT_ROOT_BUDGETS=1`) or, with `STS_SILVER_ADAPTIVE`, 10,000 for
fresh roots and 500 for a retained root whose top-two visit-share gap reaches
`STS_SILVER_ADAPTIVE_TOP_GAP`. Searched simulations are added to
`ScumSearchAgent2::simulationCountTotal`, which is default-initialized to zero
so native backends can safely accumulate counts for every default-constructed
agent. The knowledge observer is detached while searching.
`g_nativeSilverCombatStats` holds the current thread's decisions and
simulations for its latest combat.

Under Runic Dome the root uses the tracker's public pre-roll monster state and
sets `BattleContext::intentsHidden`: monster rolls (and Looter/Mugger's
post-Mug choice) are deferred in `Monster::pendingMoveRolls` until the move is
used (`takeTurn`) or queried (Spot Weakness), overrides discard them
(`cancelPendingMove`), and rollouts materialize them before deciding.
`getMoveForRoll` reads the roll-time `MonsterRollInputs`, so real play (where
`intentsHidden` is always false) is unchanged. Gambling Chip and Purity
selections are searched as whole subsets.

Each canonical monster slot carries an occupant generation. Source-qualified
splits and summons reset occupant knowledge before the first roll; Darkling
regrow retains the same identity. Lice and Darkling carry a public candidate
mask for their persistent constructor damage. A simulated world samples once
from that mask, while retained nodes, public hashes and model observations
keep the belief and redact the sample. Public hit outcomes condition the mask
without reading hidden damage. [ADR-0025](../../../decisions/0025-runic-monster-identity-and-damage-beliefs.md)
records this representation and its alternatives.

On the standard 128-seed block the native search won 86/128 against the
vendored model's 83/128 (no detectable difference;
[§348](../../experiments/ledger-06.md)).

### Live advisor

`one_combat_advisor` runs the same searcher on states from the live wire
protocol (`SilverBridge.h`). `battleContextFromWire` (`SilverWireState.cpp`)
builds the search root: the draw pile from the wire's information set, discard
and exhaust from their multisets, RNG seeded from the wire's public search
seed, and Runic Dome pending intents. At supported interrupted selections,
the producer qualifies the actual pending card queue and a typed public
action tail. Both queue kinds persist in current JSON envelopes. The importer
checks the selection's source, physical card identity, action class and
arguments before restoring the continuation. The fourteen qualified action
kinds cover draw, block, energy, damage, status changes, random upgrades,
gambling, wound shuffles and card cleanup. Unqualified tails fail closed.

For native wire roots without an observed public action tail, interrupted-card
replay reconstructs the continuation on a copy: it refunds the card's cost,
rolls back per-turn and relevant relic counters, then retains the unexecuted
work after the selection. An observed pending card queue replaces replayed
card items. Source-qualified typed tails replace the action replay, preserving
the effects already executed before the selection.
`semanticFromSearchAction` maps search actions to the
index-free `SemanticAction` the advisor lowers to live actions, and
`NativeSilverAdvisorSession` keeps one searcher per combat for reroot and
incremental budgets. The advisor uses the same equivalent-copy reroot and
translates the retained root's actions onto the live root before lowering
them, so they always name a physical card in the live hand. `test silver_wire_state` checks that live -> wire -> root equals the
backend's own root (up to discard order and the live seed), queues included,
through battles with Runic Dome, Frozen Eye and play-count relics, and that
every root action keeps its semantic identity on the live state; it counts
the roots that only lack a monster reaction separately.

## Action enumeration / semantic bridge

`search::Action::execute` and `isValidAction` define execution and legality.
The Silver search uses `Action::enumerateCardSelectActions`, including the
correct pool per task, EXHUME self-exclusion, CODEX skip, and all valid subsets
for `EXHAUST_MANY` and `GAMBLE`. Card plays are deduplicated across
search-equivalent hand copies.

Potion discard remains a legal combat action in `Action::isValidAction`.
The search prunes discard branches unless discarding a slot leaves another
Entropic Brew available and Sozu is absent; Entropic Brew's modeled effect can
fill each newly freed slot with a generated potion. Fairy in a Bottle is never
drunk (it procs on lethal), and Smoke Bomb is skipped where escape is blocked.
Alchemize is not used for the discard rule because its combat effect is not
implemented in the simulator.

A Smoke Bomb escape ends combat as `PLAYER_VICTORY` with `smokeBombUsed`, and
Silver's terminal evaluation historically scores it exactly like a win, although
the escape forfeits the combat rewards. In the 510,030-fight Silver corpus
(ledger-06), 3,765 fights start with a Smoke Bomb and about 2,923 of them end in
an escape (the other 78 of 3,001 escapes used a Brew-generated Smoke Bomb). A
seeded unit fixture shows Silver fleeing even Cultist and Jaw Worm at full HP.
`SilverEvalWeights::escapePenalty`/`eliteEscapePenalty` subtract the forfeited
rewards, capped at half the HP left when escaping, because a death also scores
positively and an uncapped penalty could make a low-HP escape look worse than
dying. Elite-trigger fights (`GameContext::isEliteTriggerCombat`) use the elite
penalty. Both default to 0 (historical behavior) until a paired gameplay gate
decides; `STS_SILVER_ESCAPE_PENALTY` enables them (#370).

`STS_MULTISELECT_MODE=all|single|none` controls subsets. `all` is default and
the complete validity contract; `single` keeps empty, singleton, and full
selections; `none` keeps only empty. `STS_MULTISELECT_CANONICAL=1` optionally
collapses masks selecting the same multiset of effect-equivalent hand cards.
Identity includes id, upgrade, turn cost, free-to-play state, and special data,
so materially distinct copies remain distinct.

At the semantic boundary (`resolveSilverSemanticAction`), an absent target
(`-1`) for an untargeted card or potion lowers to native target zero. It must
never be packed directly into the unsigned target field: that produces 8191,
which is invalid for cards and denotes discard for potions. Only
`discardPotion=true` lowers to native discard; targeted actions require an
explicit in-range target and native legality validation. The final lowered
action is revalidated against the live battle.

## Leaf/value guidance

Silver evaluates leaves by rolling out with `SilverRolloutAgent` and scoring
the terminal state with Silver's evaluation weights (`SilverEvalWeights`).
`one_combat` loads no learned combat model for play unless the research-only
`STS_SILVER_VWIN_LEAF=1` (#367) is set.

### v_win terminal pricing (#367, default off)

With `STS_SILVER_VWIN_LEAF=1`, `apps/one_combat/silver_vwin_pricer.cpp`
attaches a `SilverTerminalPricer` to each combat's searcher through
`g_nativeSilverTerminalPricerFactory`. A won terminal (a Smoke Bomb escape
included) scores `winBonus + price - turn * victoryTurnPenalty`; the price
replaces the HP, potion, gold, max-HP, death-save, Parasite and escape terms.
Losses keep Silver's shaping.

- **State priced.** The terminal's exit fields (HP, max HP, gold, stolen gold,
  potions, Writhing Mass Parasite or Omamori, spent Lizard Tail, Burning/Black
  Blood) are written into a copy of the run as `exitBattle` would, and the
  room's own continuation runs: combat rewards, an event's continuation, the
  map after an escape, or the Act 3/4 boss end. Act 1-2 boss wins get the act
  transition heal first. Rewards come from `sampleOocNoncombatFuture` copies,
  never from the real RNG; each price averages
  `STS_SILVER_VWIN_LEAF_SAMPLES` futures (default 4), shared by every price
  of the combat (common random numbers). Colosseum's Victory relics are rolled
  when the fight is chosen and are therefore the real ones.
- **Model.** DECISION screens use the ADR-0027 screen GBM
  (`sigmoid(logit(X2-B) + residual)`); the map, a following battle and
  screens the public contract cannot encode use pinned X2-B
  (`models/candidates/v_win_x2b_trees.txt`); a decided run is 0 or 1.
- **Scale.** Per combat, with the root's resources and no act heal,
  `v(1 HP)` and `v(max HP)` give an HP slope `s` (at least 0.0005); the price
  is `1 + 11 * rootPotions + (v - v(1 HP)) / s`, clamped to `[0, 3 * maxHp +
  offset]`, so a win keeps Silver's point scale (c=25 and the learned-stop
  features stay in range) while potions, gold and rewards trade in the
  combat's own HP units. When `v(max HP) - v(1 HP) <= 1e-6` (a run-ending
  boss win) the combat keeps the handcrafted formula.
- **Cost.** Prices are memoized per combat by exit fields; process totals
  print to stderr at exit. `one_combat silvervwinleafselftest` (ctest
  `silver_vwin_leaf`) checks normal, elite, Dead Adventurer and boss prices.

The engine's Dead Adventurer continuation opens its combat rewards even after
a Smoke Bomb escape (Colosseum's Victory fight forfeits them), so the pricer,
following the engine, values such an escape like a win. **Open question:**
whether that matches Java. `CombatValueNet` remains
for `vnettest`, and `CombatDistValueNet` only for `parity_test`.

Feature ordering and counts are model-interface invariants. Native PV/dist
inference may use probed OpenBLAS or scalar fallback and reports the backend.

## Diagnostics and observability

The vendored model's telemetry and diagnostics were removed (ADR-0022). The
native backend reports process totals (`nativeSilverTotals`) and per-thread
combat stats; `STS_SILVER_DEBUG_TREE` attaches the retained search graph to
advisor responses. The production search path does not depend on a diagnostic
callback.

`test silver_profile <sims> <stride>` times native Silver on fixed roots from
12 act-1–3 encounters, with one searcher per combat as in production. It
prints simulations/s and a digest of every root's edge visits, so a speed
change can be checked for exact search parity. Measured throughput (ledger
§360, 4-vCPU container): about 73k simulations/s at 10,000 simulations per
root. Rollouts (the rollout policy plus action execution) take about 73% of
instructions, node dedup about 11%, and state copies the bulk of the rest.
The profile is flat, with no function above about 6% exclusive.
`ActionQueue` copies only its queued slots. The 128-slot ring is 6.2 KB of
`BattleContext`, and slots outside the queue are never read.

Producers must record fair regime, models and relevant flags so incompatible
rows are not combined; bestbench metadata records
`effectiveCombatBackend="native_silver"`.

## Invariants / failure behavior

- Termination is `bc.outcome != Outcome::UNDECIDED`; `isBattleOver()` is
  derived.
- Search mutates copies. Only a live-valid translated action may mutate the
  committed battle.
- Search roots never carry live RNG, unobserved draw order, or a hidden rolled
  intent; the knowledge observer is detached while searching.
- Unresolved exit, empty action set, invalid edge, conversion failure, or
  model-load failure takes an explicit defensive path; it must not award
  progress, reuse stale state, or claim a model loaded.
- Terminal nodes are not expanded.
- Node/edge/searcher layout, action features, observation identity, wire
  versions, and model feature counts are interfaces. Rebuild all including
  translation units after C++ layout changes.
- Observation equality and `visibleHash` retain one field contract. Search
  transpositions use `equalForSearch`, not the hash, as identity.
- Search and diagnostics do not consume gameplay RNG merely to sample or log.
- Artifacts are active only after successful load; file presence proves
  nothing about use.
- Multi-select `all` remains the complete legal-action contract. Pruning modes
  are explicit policy-affecting opt-ins.

## Relevant tests and code

Primary code:

- `include/combat/BattleContext.h`, `src/combat/BattleContext.cpp`,
  `include/combat/CardPile.h`
- `include/sim/search/Action.h`, `src/sim/search/Action.cpp`
- `include/sim/search/SilverSearcher.h`, `src/sim/search/SilverSearcher.cpp`,
  `src/sim/search/SilverRolloutAgent.cpp`, `src/sim/search/SearchRng.cpp`
- `src/sim/search/NativeSilverBackend.cpp`, `src/sim/search/SilverConversion.cpp`,
  `src/sim/search/SilverWireState.cpp`
- `include/sim/search/ScumSearchAgent2.h`,
  `src/sim/search/ScumSearchAgent2.cpp`
- `apps/one_combat.cpp`, `apps/one_combat/native_silver_advisor.cpp`

Focused coverage includes `test battle_equality`, `card_pile`,
`card_pile_engine`, `silver_searcher`, `silver_wire_state`, `silver_profile`,
`silver_semantic_action`, `cardselect_parity`, `cardselect_canonical`,
`runic-dome-lifecycle-test`, `combat-knowledge-neutrality-test`,
`live_silver_importer_test` and `tests/live_advisor_protocol.py`. Use current
invocation details from
[build-and-debugging.md](../operations/build-and-debugging.md).

## Known limitations

- `CombatObservation` uses `CardKey` multisets and omits some transient card
  fields such as `uniqueId` and retain state.
- Exhaustive ten-card multi-select can create 1,023 subset edges. Pruning and
  canonicalization exist but are policy-affecting opt-ins.
- At a mid-card selection the advisor's root lacks monster reactions to the
  card's pre-selection effects, apart from the Guardian's deferred Mode Shift
  (see Live advisor). Copies queued by a spent
  Double Tap, Duplication or Necronomicon are present only when the producer
  sends `pendingCardQueue`, which the mod does not emit yet (issue #328).
- The Guardian's `miscInfo` is its native shift threshold, separate from the
  remaining Mode Shift power. The Java producer reads `dmgThreshold`,
  `dmgThresholdIncrease` and `isOpen`: Java increments on entering Defensive
  Mode, while native increments on Twin Slam, so the defensive projection
  subtracts the increment (10). This also works without an earlier observation
  of the fight. Missing fields or a non-vanilla increment remain unsupported.
- Terminal run-value guidance depends on its evaluator's feature coverage and
  never substitutes for exact terminal combat utility.

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


### Final Silver root selection and narrow useless-action diagnostic

`SilverSearcher::bestAction()` selects the edge with the largest
`Edge::visitCount`. It updates only on strict `>`, so ties keep the first
**enumerated edge**, including an all-zero tie. Mean Q, exploration/UCB score,
prior and child-node visit count are not final-selection tie-breaks. This same
method serves flat/adaptive/exact budgets, retained roots, singleton bypasses,
and `NativeSilverAdvisorSession::result`. Retained edge visits participate in
the choice; counts are not restricted to new simulations at the current root.
UCB/Q still affect tree allocation before this final choice. There is no root
prior in the active Silver backend.

The backend maps the chosen action's card identity to the concrete live state
with `translateAction`, including equivalent-copy mapping, and fails if it is
illegal. The advisor performs that mapping and semantic lowering; a lowering
failure rejects the response. These transformations express the selected
semantic action rather than reranking candidates. The adapter's diagnostic
Q is `child.evaluationSum / child.simulationCount`; it is a heuristic value,
not a probability or the final selection score.

`STS_SILVER_USELESS_TRACE=/path/to/fresh.jsonl` records a census after the real
root action is selected. The initial qualified class is deliberately narrow:
a legal energy-spending red Defend is the only card in hand, no potion remains,
no player power/status is present, only Burning Blood (or no relic) is allowed,
and no live enemy currently has an attack intent. The play must leave an empty
hand and no other decision besides End Turn, increase block, spend energy,
and leave HP, monsters and RNG unchanged immediately. Relic/power/retention/
card-draw/attack/unforced cases fail closed.

The proof executes two copied continuations: Defend then forced End Turn,
versus End Turn immediately. Both must reach the same next-turn player
boundary while undecided. `BattleContext::operator==` then compares all
ordered card piles, Player/Monster fields, flags, counters and all six RNG
streams, with only these explicit exceptions:

- `energyWasted` is reported separately; it changes Silver's non-victory
  heuristic (`-1.75 * energyWasted`, except shape encounters), not gameplay.
- Extra execution-loop steps on the Defend branch are reported. The comparator
  must have at least as much loop-guard headroom; roots near a guard are rejected.
- The static benchmark `sum` sink is excluded by the existing equality operator;
  it has no gameplay/search-selection role.

Thus `provably_useless` means this **frozen concrete state and its forced
End-Turn continuation** has an equivalent mechanical continuation (or more
loop headroom with the comparator). It does not assert equivalence for other
hidden RNG states, other block cards, or optional continuations. Diagnostic
copies suspend the live knowledge observer and restore the debug pointer.
The result is never used to choose/prune an action or change a budget.

Verified rows contain seed/floor/turn/decision identity, snapshot fingerprint
and full binary snapshot, selected/comparator actions, all root edge visits
and child Q denominators, configured/completed simulations, and the proof's
resource/counter differences. Snapshot round-trip must preserve the root's
search state, ordered cards and RNG before a result is accepted. The verifier
`bash tools/seed_guard.sh build/.../silver_useless_replay TRACE.jsonl` replays
all verified examples (up to 128 locally). `tools/analyze_silver_useless.py`
checks final-selection/Q accounting and groups higher-Q, near-equal-Q and
lower-Q-but-selected cases. Its absolute 1e-6 near-Q band is a descriptive
label, not a confidence interval. A zero census does not establish absence of
other wasted-block classes. No policy fix follows from these diagnostics alone.
### Silver tree profile

`STS_SILVER_TREE_PROFILE=/path/to/fresh.jsonl` enables aggregate diagnostics
for real decisions executed by `NativeSilverBackend` (not the separate live
advisor path). Unset/empty means no file and no histogram updates. The writer
serializes rows across worker threads; a failed open/write is an explicit error.
The profile does not change policy, budgets, evaluation, or RNG. Rows identify
seed, act/floor, encounter, room, turn, decision, player/enemy HP, configured
maximum budget, actual completed simulations, allocated nodes, root actions,
inherited visits, selected action, and singleton skips.

The denominator is **newly completed simulations in this real decision**,
including both adaptive chunks but excluding all inherited visits and terminal
root initialization. Singleton skips have zero samples. Each completed step
calls the heuristic evaluator once; Native Silver has no neural leaf evaluator.
Endpoint counts sum to completed simulations. Descent-bound exceptions are
recorded separately in an error row and rethrown; analysis rejects incomplete
searches instead of including their partial counts. The analyzer requires explicit
boolean budget-mode flags, zero completed simulations for singleton skips, the
full configured budget for flat searches, and exactly 500 or 10,000 completed
simulations with a 10,000 maximum for adaptive searches.

Endpoint classes follow simulator outcomes: `victory` includes escapes the
engine treats as victory; `death` requires PLAYER_LOSS with HP <= 0;
`turn_limit` is a PLAYER_LOSS beyond turn 500; `engine_stop` is any other
PLAYER_LOSS (including no-damage/loop-guard stops); `nonterminal` is UNDECIDED
when no supported action is available. Turn-limit classification takes
precedence over HP. Engine losses must not be interpreted as sampled deaths.

Tree depth counts selected action edges from the current root; chance-outcome
edges do not add a second action. Total endpoint depth adds rollout actions.
A newly reached nonterminal tree leaf normally receives a SilverRolloutAgent
rollout before heuristic evaluation, so terminal **evaluated endpoints** do
not imply terminal tree leaves. `nonterminal_rollout_starts` and `rollout_calls`
make this distinction visible; cycle rollouts are counted separately. Exact
histograms retain maxima and quantiles without dumping states or whole trees.

Run `python3 tools/analyze_silver_tree_profile.py PROFILE.jsonl --output
SUMMARY.json` to validate all denominators and generate counts/shares and depth
quantiles by act, room, encounter, turn, decision, HP quarter, enemy HP in
25-point bands, and configured budget. The report ranks encounters with at
least 20 observed decisions (override `--minimum-decisions`) and includes one
complete fight's evolution per encounter. It uses simulation-weighted shares,
not averages of per-decision percentages. Zero-sample shares are null. Reused
visits and correlated search samples are not independent gameplay outcomes;
terminal reachability alone establishes no search-quality or budget claim.
