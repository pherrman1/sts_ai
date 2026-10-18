# Combat search

Last verified: 2026-10-18 for §523 random playouts per leaf; 2026-10-17 for the live advisor rollout root table (ADR-0046); 2026-10-17 for the per-playout action cap (#544) and its `STS_SILVER_ROLLOUT_ACTION_CAP` switch; 2026-10-17 for the zero-cost rollout cap and depth-backstop rollout (#544); 2026-10-17 for the root-prior override used by the OOC Silver fallback and the burning-elite escape rule; 2026-10-15 for the default rollout card table (ADR-0040) and the §479 rollout research options; 2026-10-14 for default canonical multi-select masks (ADR-0034) and the §473 escape-penalty gate and defaults (ADR-0036, ADR-0037); 2026-10-08 for targeted public capture and the bounded public pair probe;
2026-09-25 for native-only Silver (ADR-0022), the native default
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
At A20 with student C out of combat (§516, 512 paired full runs), learned
stopping matched flat exact 10k (Heart kills 30 vs 27, reached Act 4 −0.4 pp
[−3.4, +2.6]) at 0.41x the run CPU; adding the gen-6 MLP prior as root and
tree prior (`STS_SILVER_TREE_PRIOR_MIN_VISITS=8`) reached Act 4 more often
(+3.9 pp, not pre-registered) without more Heart kills.

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

A live combat that exceeds 1,000 decisions fails with `stall: exceeded 1000
decisions`. Free loops can reach it: with Medical Kit, Dark Embrace, Feel No
Pain and the Chosen's Hex, playing a Dazed costs nothing, draws a card,
gains block (capped at 999) and shuffles a new Dazed in, and Silver scores
that play slightly above End Turn at every root (seed 86001271, floor 18).
`STS_SILVER_LOOP_GUARD` (default 50) counts consecutive live decisions in one
player turn whose state differs from the previous decision's only outside a
progress fingerprint (player HP and strength, an energy drop, and each
monster's HP, block, liveness, strength, Vulnerable, Weak, Artifact and status
flags; piles, hand and player block are excluded). At the cap, in a
`PLAYER_NORMAL` state where End Turn is legal, End Turn is committed without
search and the count resets. The guard only reads the live state, so a combat
that never reaches the cap plays exactly as without it; the skipped root is
not passed to root observers or traces.

Every Silver playout inside search also stops after 1,000 actions, including
card selections and uniform-policy actions. This bound is independent of the
live decision guard and the rollout agent's per-turn card-play counter. A
capped playout keeps its unresolved state and uses the existing heuristic
value; it does not fabricate a terminal outcome. `SilverSearchStats` records
`rolloutActionLimitHits`, and endpoint profiling records the capped state as
`nonterminal`. Shorter playouts retain their action/RNG behavior. This bounds
free draw/reshuffle loops at the playout decision boundary (#544); it does not
bound work inside a single simulator action. The cap changes default play where a
playout runs longer than 1,000 actions (A0 seed 111139580 dies on floor 50 instead
of reaching floor 55). `STS_SILVER_ROLLOUT_ACTION_CAP=N` sets it, and `0` restores
uncapped playouts.

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
penalty. Native Silver uses 12 and 35 by default (ADR-0036);
`STS_SILVER_ESCAPE_PENALTY=0,0` restores the historical escape-as-win score
(#370). The live-game advisor (`native_silver_advisor.cpp`) uses the same
`12,35` without reading the environment, and the wire context marks elite fights
by encounter (ADR-0037); the synthetic-prior generator copies the backend's
weights. The `SilverEvalWeights` struct defaults stay 0. Before PR #540
`one_combat` rejected the variable at startup. The only gameplay gate, ledger-06
§473 (`12,35` vs `0,0` on the `off` stack, 500 paired seeds per cohort), is
NOT_SHOWN at A0 (414 vs 414 wins) and at A20 (floor +0.024 [−0.168, +0.234]);
only 46 and 21 pairs differ at all. The default follows Philipp's decision.

Native Silver never considers Smoke Bomb in the act-3 burning elite while keys
are collected and the Emerald Key is missing (`SilverSearchContext::escapeForfeitsRun`,
set in `NativeSilverBackend.cpp`). No later map has a burning elite, so that
escape rules out the Heart (ADR-0041), which the reward penalty does not price.
The live wire carries no keys or map, so the advisor path does not apply it.

Held potions score `potionWeight` = 11 each at a victory leaf. Ledger-06 §510
measured potion prices at A20 by paired continuation (`potionpriceprobe`: one
potion removed vs unchanged, next 3 fights played, then the A20 floor model,
calibrated by a −12 HP copy). The pooled price is 9.9 HP-eq [7.9, 12.3],
consistent with 11 (pre-registered). Fairy in a Bottle is also scored by the
death-save term (+0.3 × max HP, 0.6 with Sacred Bark), and without Fairy potions
price at 7.8 [6.1, 9.8]; **Inference:** the flat 11 may overprice non-Fairy
potions (post hoc). Per-type prices differ: Fairy about 44, Attack/Blood/Skill
potions 15–21, Block/Weak/Swift/Speed/Essence of Steel near 0. Apart from the
Fairy death-save term the default formula has no per-type weights.
Research-only `STS_SILVER_POTION_WEIGHTS=NAME=w,...[,*=w]` (Potion enum names;
unlisted types take `*`, else 11; an unknown name aborts) replaces the count
with per-type weights in native Silver (`one_combat`); the live advisor ignores
it. Ledger-06 §513 (A20, student C OOC, 128 paired seeds) did not show an effect (NOT_SHOWN) of
the §510-derived per-type weights or a flat 7.8 vs flat 11: floors −1.37
[−3.45, +0.74] and −0.80 [−2.96, +1.36]. The flat 11 stays.

HP in the victory leaf is linear. In the §510 paired continuations one HP at
< 30% of max HP was worth ~4x the mean HP slope (A20 floor model) and one HP at
≥ 90% ~0.5x; the formula's implied death price (~110 HP) was below the measured
~200 (re-analysis, `/mnt/project-files/silver-leaf-eval/END-STATE-FORMULA.md`).
Research-only `STS_SILVER_CONCAVE_HP_LEAF=k` (native Silver; per-copy
override `g_nativeSilverConcaveHpLeafOverride` for `potionpriceprobe`
`leaf:concave=K` variants) replaces `h` by a concave `u(h)` with slope 1 at 75%
HP and scales the potion term by `sqrt(u'(h))`; the loss branch and the
final-fight leaf are unchanged. Test: §TBD (pre-registration
`docs/experiments/evidence/silver_concave_hp_leaf_20261018/PREREG.md`).

`STS_MULTISELECT_MODE=all|single|none` controls subsets. `all` is default and
the complete validity contract; `single` keeps empty, singleton, and full
selections; `none` keeps only empty. By default (ADR-0034) masks selecting the
same multiset of effect-equivalent hand cards collapse to one;
`STS_MULTISELECT_CANONICAL=0` restores every valid mask.
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
Each `SilverSearcher` carries a `RolloutConfig` (uniform-random playouts, greedy
playouts per leaf, card-play table), read from the `STS_SILVER_ROLLOUT_*`
research variables and overridable per thread with
`g_nativeSilverRolloutOverride`; the default is one greedy playout whose
card-play order comes from the gen-6-fitted table in
`SilverRolloutCardTable.h` (ADR-0040; `STS_SILVER_ROLLOUT_CARD_TABLE=0`
restores the hand-written `cardPlayPriorities` order). The
`ctmsilvergen` armset `rollout479` compares these per arm on the same captured
fights. §479 (A20, 689 fights): uniform playouts lose 22.8 fight score at no
CPU saving per simulation; a learned card table and 2 or 4 playouts per leaf
at matched rollouts per decision are not shown better, so the greedy single
playout stays; Philipp then made the table the default (ADR-0040). §523 (A20, 176 fights): averaging 1, 2, 4 or 8 uniform random playouts per leaf
loses 31–35 fight score to greedy at every k (0.85x–4.70x CPU per fight); more random playouts barely help.
Default since ADR-0046 (`STS_SILVER_ROLLOUT_ROOT_TABLE`: unset = bundled
`models/combat_policy_mlp_g6_E.txt`, `0` = the fixed ADR-0040 table, or another
`combat_policy_mlp` model): that fixed table is replaced by one built once per searched root
(`nativeSilverRolloutRootTable`). The model scores every distinct card (id and
upgrade) in hand, draw and discard pile as a play at the root state, aimed
where the rollout aims it (attacks at the lowest-HP monster, other targeted
cards at the highest). Every playout of that search uses those scores as its
card-play order; cards not in those piles (made during the playout) keep their
ADR-0040 entry, shifted by the mean gap between the two scales. The rollout's
category rules (zero-cost first, block check, AoE) are unchanged. Cost is one
prior call per root, not per playout step. The `ctmsilvergen` armset `roottable`
compares `greedy<b>` and `roottable<b>` (model `STS_CTMSILVER_ROOT_TABLE_MODEL`)
at each budget in `STS_CTMSILVER_SWEEP_SIMS`; per-thread override
`g_nativeSilverRolloutRootTableOverride`. §519 (A20, gen-6 E, 1,426 fights): at
equal simulations the root table scores +2.7 [+0.6, +4.8] better, but it costs
5.1% more CPU per simulation (longer playouts plus the build), and against
greedy at 6% more simulations it is +1.9 [−0.1, +3.9] at 1.007x CPU per fight:
not CPU-matched and not shown. §521 repeats it at 10k: +1.8
[−0.4, +4.0] against greedy at 10,700 at 1.008x CPU per fight (NOT_CPU_MATCHED,
NOT_SHOWN), +1.8 [−0.2, +3.9] at equal simulations; 7% more greedy simulations
buy nothing at 10k (−0.02). Philipp made it the default anyway (ADR-0046); the
`roottable` armset requires `STS_SILVER_ROLLOUT_ROOT_TABLE=0`. The live advisor
does the same in every `NativeSilverAdvisorSession::decide` (extends keep that
root's table): `one_combat_advisor` loads the model once at start, unset =
`models/combat_policy_mlp_g6_E.txt` beside the executable (the installed release,
which `tools/live_game_runtime.py` pins as `rolloutRootTableSha256`), else under the
working directory; `0` restores the ADR-0040 table, a model that does not load
exits 2, and each Silver evaluator reports `rolloutRootTable` (model fingerprint or `off`).
From the 50th card played in a turn, the greedy playout no longer gives
zero-cost non-attacks first priority, so a replayable zero-cost draw (two
Finesse, Deep Breath) cannot loop to the 1000-card per-turn cap every turn
without attacking (#544: such playouts ran about 143k actions to the engine
loop guard). The cap also fires in long non-looping turns (for example
Corruption decks), where free skills past the 50th card are no longer played
first. `STS_SILVER_ROLLOUT_ZERO_COST_CAP=N` sets it, and `0` restores the
uncapped order. A tree descent that passes the 5000-node depth backstop now ends in
a rollout from the current node, counted in `descentBoundRollouts`, instead of
throwing `SilverSearcher::step descent exceeded depth bound`.
`one_combat` loads no learned combat model for play. `CombatValueNet` remains
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
Decision states freed by compaction or by a finished searcher go to a
per-thread pool that the next searcher reuses, and a new node takes one copy
of the expansion scratch instead of a `std::swap` (`BattleContext` has no move
operations, so the swap made three copies). `nodeCount()`, which drives the
reuse cap, is unchanged; play is bit-identical (ledger §436). The pool keeps
up to 65,536 states (about 0.5 GB) per thread; measured peak memory rose by
27–46 MB. It dies at thread exit, so a searcher must never be owned by a
global, static or thread_local object.

`one_combat silversynthgen N SIMS ASC OUT_PREFIX SEED TEACHER natural|perturbed`
is a research-only corpus producer for a learned Silver root prior and leaf
value (flat exact-10k teacher from `tools/silver_synth_teacher.py`). Two
default-off thread-local hooks in `NativeSilverBackend.h` carry it:
`g_nativeSilverRootObserver` sees every root after its search and before the
action is committed, and `g_nativeSilverLeafSamples` attaches a
`SilverLeafSamples` sampler that copies every 2,503rd nonterminal rollout start
with its rollout value. Neither changes selection, evaluation or any RNG draw
(`test silver_searcher`); a natural seed's rows are byte-identical across runs.
Each root row holds the search-state wire and the root edges' visits and Q. On
one root in four, a fresh independent 10k search is added. On one in eight,
two Silver continuation labels per root action are added (2,000 simulations
per decision, with planner randomness independent of the sampled world). The
labels are scored by the root's own terminal evaluation. `perturbed` records
a detached copy of each fight with a random HP, card, upgrade and potion
change, while the run continues through the unperturbed fight.

The corpus's offline harness rebuilds each recorded state from its wire and
plays no game seed. `one_combat silversynthfeatures OUT_PREFIX < corpus.jsonl`
writes sparse `combatExtractFeatures` rows (plus `combatFillActionFeatures` per
root action) for leaves, roots and, on continuation roots, each action's child
states. These are the generator's two label children (same keys in
`apps/one_combat/silver_synth_keys.h`) and one probe child with four
independent rollouts. `one_combat silversynthreplay` reads one root task per
line and reports the most visited action at each budget of a fresh search,
optionally with the research-only root prior bonus
(`SilverSearcher::rootPrior`/`rootPriorWeight`, default off): a visited root
edge scores `weight * P(a) / (visits + 1)` on top of UCB, and unvisited edges
stay `+inf`. `tools/silver_synth_gates.py` trains the LightGBM models and
computes the pilot's Gate A/B. On the 89 smoke roots with a second teacher, a
plain 10k replay from the wire picked the recorded top action on 69, and the
independent second teacher on 66.

The same bonus runs in live play as a research-only option (default off):
`STS_SILVER_ROOT_PRIOR=<model>` with `STS_SILVER_ROOT_PRIOR_WEIGHT=<w>` makes the
native backend score every searched root's actions with a
`combat_policy_trees_v1` tree ensemble (`CombatValueNet`, policy layout). The
model is exported from LightGBM by `silver_synth_gates.py export`. Its sigmoid
outputs, normalized over the root, become `rootPrior`; roots with one action
get none. The prior is recomputed after every reroot, so inherited visits damp
it. `bestbench` sidecars record the model path, SHA-256 and weight. Learned
stopping was not retrained for it. Its online screen was negative (§399).
`STS_SILVER_ROOT_PRIOR_SCOPE=override` (research) keeps the loaded prior off
unless a thread override turns it on; the OOC MCTS Silver resolver
(`STS_OOC_MCTS_COMBAT_RESOLVER=silver`) uses it so that imagined combats use the
prior while live combats stay plain; the opt-in Silver fallback for CTM-refused
combats (`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS`) sets the override off. `all` (the default) applies it everywhere.

A research-only tree prior extends the same model below the root (ledger
§452): when `SilverSearcher::nodePrior` is set, a non-root decision node with
at least `treePriorMinVisits` simulations is scored once (cached on the node)
and its visited edges get the same bonus; wherever a prior is known, untried
edges are tried in descending prior order. The backend enables it only through
the thread override `g_nativeSilverTreePriorOverride` (K), on searches that
have a root prior, or for whole runs through `STS_SILVER_TREE_PRIOR_MIN_VISITS=K`
(research, default 0 = off; requires `STS_SILVER_ROOT_PRIOR`; ignored on
searches where a thread sets the root-prior override, so research arms keep
their own setting); `ctmsilvergen` with `STS_CTMSILVER_ARMSET=treeprior452`
(or `treeprior452k8`) uses it for paired fight-level arms at 2k. At equal 2k
simulations K = 8 raised the fight score over plain 2k (+1.17 [+0.53, +1.79]),
at 2.9x the CPU. At matched CPU (§453, `cpumatch453`) it was not shown to
beat plain 6k (+0.46 [−0.02, +0.97]); it stays research only.
The prior is scored by `CombatValueNet::predictPolicyActions` (§454): one state
extraction per node, edges with bit-identical action features scored once, and
a compact copy of the tree ensemble in which each tree's state-only prefix is
walked once per node and the edges finish in lockstep. Scores equal `predictVec`
bit for bit, so search results are unchanged; K = 8 then costs about 1.7x and
K = 1 about 4.8x the CPU of plain 2k per decision. The remaining overhead is
almost all tree walking (about 74 scored nodes per 2k-simulation decision at
K = 8, about 2,000 trees each).

The same prior hook also takes a factorized MLP (`combat_policy_mlp_v1`,
research, default off; the Silver AlphaZero-style loop,
`/mnt/project-files/silver-az-mlp/PLAN.md`). `CombatValueNet::load` accepts it
for `STS_SILVER_ROOT_PRIOR`, and `nativeSilverPolicyPrior` then scores edges
with `predictPolicyMlp` and normalizes with a softmax instead of
sigmoid-then-normalize (the tree path is unchanged). The state layer runs once
per node over the nonzero state features; per edge the net adds the action
block, a card-embedding row for `aCardId` and the targeted monster's nine slot
features (`combatActionTargetSlot`), then two ReLU layers; edges with equal
action blocks and target are scored once. A `combat_policy_mlp_v2` file adds
optional tables (`enc`, `mon_id`, `mon_dmg`, 128 x h1 each) after the v1 body:
one per-node row for the encounter id and, per occupied monster slot, rows for
id + 1 and for its incoming damage (feature `mKIntent`, which is the damage, not
an intent category). Without them the state layer sees these values only as
plain numbers. Loaders older than v2 reject the header instead of dropping the
tables, and a v1 file with tables does not load; v1 files score as before
(`docs/experiments/evidence/silver_prior_arch_20261014/`).
`tools/silver_az_mlp.py` featurizes the synthetic corpus (`silversynthfeatures`
action rows carry `tgt`), trains
from random initialization, and exports the model with input scales and the
embedding projection folded in. `one_combat silverpolicymlpcheck MODEL PREFIX
OUT [GBM]` writes the native logits of a feature file for the Python parity
check and times the MLP (and optionally a tree prior) per root. `ctmsilvergen`
with `STS_CTMSILVER_ARMSET=mlpprior` runs `plain2k`, `plain_cpu` (budget
`STS_CTMSILVER_PLAIN_CPU_SIMS`) and `mlp8_2k` (K = 8, scored by
`STS_CTMSILVER_MLP_PRIOR` through the thread override
`g_nativeSilverPriorNetOverride`; `STS_CTMSILVER_MLP_PRIOR_PREV` adds
`mlp_prev8_2k`); `STS_SILVER_ROOT_PRIOR` and its weight must still be set.
The generation-1 model (`/mnt/project-files/silver-az-mlp/gen1/`) at K = 8 and
2k costs about 1.05x plain 2k per fight and beat plain 2,300 simulations
(1.16x) by +0.91 fight score [+0.43, +1.40] on 3,409 paired fights (§455), the
first prior shown to help at matched CPU; it stays opt-in.
Generation 3 (self-play with gen 2, then gen 3 as prior;
`/mnt/project-files/silver-az-mlp/gen3/model/`) beat plain 2,300 by +1.50
[+0.94, +2.09] on 3,275 fights at 1.06x plain 2k but was not shown better than
generation 1 (+0.14 [−0.39, +0.66]) (§460).
Generations 4–6 raised the self-play teacher to 10k, 20k and 40k simulations and were gated offline
only (orig fold-4 CE 1.2103, 1.1954, then 1.1749); generation 6 is the v2 model with encounter and
monster tables, trained from scratch with distillation from a 512/256 net
(`/mnt/project-files/silver-az-mlp/gen6/model/combat_policy_mlp_g6_E.txt`; §465, §477, §478). At A20, gen 6
at K = 8 beat plain Silver at equal simulations at 2,500 (+3.85 fight score [+1.23, +6.52]) and
625 (+2.56 [+0.40, +4.74]) but not at 10,000 (+0.73 [−1.45, +2.91]), and was not shown better
than gen 5 at any budget (§476).
`STS_CTMSILVER_ARMSET=mlpsweep` (§476) instead runs, for every budget in
`STS_CTMSILVER_SWEEP_SIMS`, `plain<b>`, `mlp<b>` (K = 8, `STS_CTMSILVER_MLP_PRIOR`)
and `mlpprev<b>` (`STS_CTMSILVER_MLP_PRIOR_PREV`); it is the only armset that
accepts Ascension 20, and `STS_CTMSILVER_HALLWAY_EVERY = n` replays only about
one normal fight in n (hash of seed and fight index).
Self-play data for later generations comes from `one_combat silverazgen N SIMS
ASC OUT_PREFIX SEED natural|perturbed TREE_MIN_VISITS ROOT_BONUS`: the
`silversynthgen` runs and root/fight rows without the second teacher,
continuations or leaf samples, where every fight of the run searches with the
`STS_SILVER_ROOT_PRIOR` MLP as tree prior at K = `TREE_MIN_VISITS`.
`ROOT_BONUS 0` (the plan's teacher) sets the thread override
`g_nativeSilverRootPriorBonusOff`, which turns off only the root bonus
(`SilverSearcher::rootPriorBonus`); the tree bonus and the prior-ordered first
tries at the root stay. The manifest records the model hash, K, the weight,
the `STS_*` environment and the OOC policy.
`one_combat silverazfocusgen N SIMS ASC OUT_PREFIX SEED ENCOUNTER REPLICATES
OTHER_SIMS TREE_MIN_VISITS ROOT_BONUS` records one encounter only (data for a
fight-specific prior): other fights play unrecorded at `OTHER_SIMS` with the
same prior; the first `ENCOUNTER` fight of the run is recorded as `REPLICATES`
detached copies at `SIMS` (copy 0 unperturbed, the rest perturbed as in
`silversynthgen`; fight id = fight + 1000 × copy), and the run then ends. A boss
encounter is forced as its act's boss by overwriting `gc.boss` (no game RNG is
drawn). The manifest adds a `focus` block.
`one_combat silverfocusevalgen N ASC OUT_PREFIX SEED ENCOUNTER REPLICATES OTHER_SIMS
ARM_SIMS TREE_MIN_VISITS PRIOR_A PRIOR_B` is the paired online check for such a prior: it reaches the
encounter the same way (root bonus on), then plays `REPLICATES` copies of the fight per arm at
`ARM_SIMS` with that arm's MLP as root and tree prior (via `g_nativeSilverPriorNetOverride`). Copy r
of both arms shares one battle seed (copy 0 the natural one; the battle reseeds its combat streams
from `gc.seed + floor`, so copies r ≥ 1 set a fresh `gc.seed`) and one Silver planner seed, so the arms
differ only in the prior; with `PRIOR_A = PRIOR_B` the rows match exactly.

Producers must record fair regime, models and relevant flags so incompatible
rows are not combined; bestbench metadata records
`effectiveCombatBackend="native_silver"`.

### Targeted public decision capture and pair probe

The default-off `STS_SILVER_PUBLIC_TRACE` and `STS_SILVER_PUBLIC_TARGET=SEED:FLOOR`
controls must be supplied together. They record the supported public wire state,
selected semantic action and existing root alternatives/statistics at the named
combat. The wire's isolated search seed is zero; the outer source seed is a
replay locator. Capture adds no simulations and does not export a private
snapshot. Unsupported public conversion is explicit, and child values can
include inherited samples rather than newly evaluated independent rollouts.

The separate CMake target `silver-public-pair-probe` builds
`silver_public_pair_probe SPEC.json check|canary|evaluation [K]`. It is a bounded
research executable for one hash-bound Champ decision and two declared actions,
not a general gameplay backend. It samples public-compatible futures, lowers
semantic actions through the existing bridge, and rebuilds a public planner
root for every subsequent decision under fresh exact-10,000 search. Supported
wire round-trip equality is required. It does not reconstruct the original
retained learned-stop controller, historical private RNG or an arbitrary saved
combat. Its endpoint is conditional combat survival, not whole-run Act-3
strength. Source and protocol are routed by
[the campaign packet](../../experiments/evidence/ironclad_a0_overnight_20261008/README.md).

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
- Mid-card selections require an explicitly qualified public continuation.
  Java captures verified pending card/action queues, including vanilla Double
  Tap, Duplication and Necronomicon copies. Unknown owners, callbacks or queued
  effects remain unsupported; see the [live continuation contract](../operations/live-model-inspector.md).
- The Guardian's `miscInfo` is its native shift threshold, separate from the
  remaining Mode Shift power. The Java producer reads `dmgThreshold`,
  `dmgThresholdIncrease` and `isOpen`: Java increments on entering Defensive
  Mode, while native increments on Twin Slam, so the defensive projection
  subtracts the increment (10). This also works without an earlier observation
  of the fight. Native phase parity covers A0/A9/A19/A20 thresholds. Captured
  A20 offense-after-damage, defense and return-to-offense roots are replayed by
  `live_silver_importer_test`; live MCP and accepted Silver roots agreed on the
  threshold sequence 40, 40, 50. Missing fields or a non-vanilla increment remain unsupported.
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
