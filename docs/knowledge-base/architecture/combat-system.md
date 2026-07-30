# Combat system

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## State boundary

`BattleContext` is the complete mutable combat state used by action execution
and search. It owns six combat RNG streams, player and monster state, card and
action queues, potions, turn state, and the terminal `Outcome`
(`include/combat/BattleContext.h`, `BattleContext`). `BattleContext::init`
resets nested state and derives battle state from a `GameContext`;
`BattleContext::exitBattle` transfers HP/max HP, gold, potions, six combat RNG
states, selected persistent card/relic effects, and the combat outcome back to
the run (`src/combat/BattleContext.cpp`,
`BattleContext::init`, `BattleContext::exitBattle`,
`BattleContext::updateRelicsOnExit`, `BattleContext::updateCardsOnExit`).

`BattleContext::executeActions` drains the internal queues until the engine
needs player input or reaches a terminal state. `search::Action::execute`
translates a packed card, potion, selection, or end-turn choice into mutations
of that engine (`src/combat/BattleContext.cpp`,
`BattleContext::executeActions`; `include/sim/search/Action.h`, `ActionType`;
`src/sim/search/Action.cpp`, `Action::execute`).

## Decision flow

1. `ScumSearchAgent2::playoutBattle` selects fair or known-RNG handling and a
   searcher (`src/sim/search/ScumSearchAgent2.cpp`,
   `ScumSearchAgent2::playoutBattle`).
2. In fair play, `ScumSearchAgent2::playoutBattleFair` searches one observed
   decision, commits the most-visited legal root action, and reconstructs a
   search for the next observation (`ScumSearchAgent2::playoutBattleFair`).
3. With Searcher3, `BattleScumSearcher3::step` samples a hidden-state particle,
   applies it to a copy of the root battle, enumerates legal actions, selects
   edges, rolls out or evaluates a leaf, and backpropagates the result
   (`src/sim/search/BattleScumSearcher3.cpp`,
   `BattleScumSearcher3::step`, `enumerateActionsForNode`,
   `BattleScumSearcher3::playoutRandom`,
   `BattleScumSearcher3::backpropagate`).
4. `BattleScumSearcher3::selectBestEdgePUCT` uses PUCT when a policy or PV
   model is active and UCB-style exploration otherwise
   (`src/sim/search/BattleScumSearcher3.cpp`,
   `BattleScumSearcher3::selectBestEdgePUCT`).

Searcher2 is the default engine (`g_useSearcher3=false`) and supports tree
reuse in known-RNG play. Searcher3 is opt-in via `STS_SEARCHER3=1`; it stores a
cached observation per node and one searcher-level particle belief
(`include/sim/search/BattleScumSearcher2.h`,
`BattleScumSearcher2`; `include/sim/search/BattleScumSearcher3.h`,
`BattleScumSearcher3::Node`, `Belief`).

## Observations and hidden state

`CombatObservation::fromBattleContext` builds the state Searcher3 treats as
visible, and `CombatObservation::visibleHash` hashes part of it.
`HiddenBattleState` contains a sampled draw order and six RNG seed pairs;
`Belief::initial` creates particles and `Belief::sample` chooses uniformly
(`include/sim/search/CombatObservation.h`, `CombatObservation`,
`HiddenBattleState`, `Belief`; `src/sim/search/CombatObservation.cpp`, named
methods).

The belief implementation is incomplete: `Belief::update` is a no-op,
`Belief::sample` ignores weights, and Searcher3 mutates the single belief while
walking simulated paths. `CombatObservation::operator==` omits draw-pile
contents and several fields that `visibleHash` includes, while the hash omits
other observation fields such as powers, stance, relic counters, and input
legality. It is therefore not a complete observation identity or a conditioned
Bayesian belief (`src/sim/search/CombatObservation.cpp`, `operator==`,
`visibleHash`, `Belief::update`, `Belief::sample`). No automated test covers
these contracts.

The canonical learned-combat input has 1,766 state features and the policy
edge representation has 14 action features. Producer order comes from
`combatFeatureNames`/`combatExtractFeatures` and
`combatPolicyFeatureNames`/`combatFillActionFeatures`
(`src/sim/search/CombatValueNet.cpp`, named functions). `DATA_SCHEMA.md`
documents the same 1,766 + 14 layout. Training and native inference must use
that exact order.

## Learned guidance

`CombatValueNet`, `CombatDistValueNet`, and `CombatPVNet` load native artifacts
and score combat states or edges (`include/sim/search/CombatValueNet.h`,
`CombatValueNet`; `include/sim/search/CombatDistValueNet.h`,
`CombatDistValueNet`; `include/sim/search/CombatPVNet.h`, `CombatPVNet`).
`apps/one_combat.cpp` `main` activates them with `STS_VNET`, distribution/PV
flags, and `STS_POLICY`; each searcher has a `computeEdgePriors` implementation
for the separate policy model (`src/sim/search/BattleScumSearcher2.cpp` and
`src/sim/search/BattleScumSearcher3.cpp`, `computeEdgePriors`). The global
PUCT constant defaults to 2.5 (`src/sim/search/CombatValueNet.cpp`, `g_cPuct`).

## Known discrepancies and risks

- `STS_FAIR=1` does not imply Searcher3. Default Searcher2 shuffles the draw
  pile and replaces only `shuffleRng` and `cardRandomRng`; future AI, misc,
  monster-HP, and potion RNG states remain concrete. Searcher3 randomizes all
  six streams but has the belief limitations above
  (`src/sim/search/BattleScumSearcher2.cpp`, `determinize`;
  `src/sim/search/BattleScumSearcher3.cpp`, `applyParticle`). Fair play is a
  repository evaluation label, not proof that every hidden variable is modeled.
- Combat loops must use `bc.outcome == Outcome::UNDECIDED`. `isBattleOver` is
  reset in `BattleContext::init` and read in `afterMonsterTurns`, but no current
  code assigns it `true`; agent loops correctly use `outcome`
  (`src/combat/BattleContext.cpp`, `init`, `afterMonsterTurns`;
  `src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair`,
  `playoutBattle`).
- **Discrepancy:** comments advertise Searcher3 RNG seeding from `agentSeed`,
  observation hash, and decision index. The constructor seeds before
  `ScumSearchAgent2` assigns `s3.agentSeed = bc.seed`, and `decisionIndex` is
  never assigned anywhere. Both advertised inputs are therefore zero during
  construction
  (`src/sim/search/BattleScumSearcher3.cpp`,
  `BattleScumSearcher3::BattleScumSearcher3`;
  `src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair` and
  `playoutBattle`; `include/sim/search/BattleScumSearcher3.h`, member defaults).
- **Discrepancy:** Searcher3 expansion calls `computeEdgePriors` only when the
  separate policy net is enabled, while PUCT selection also recognizes a
  loaded PVNet (`src/sim/search/BattleScumSearcher3.cpp`,
  `BattleScumSearcher3::step` and `selectBestEdgePUCT`). PVNet-only operation
  therefore leaves the default zero priors on multi-edge nodes.
- Native PV/value implementations dynamically load a hard-coded SciPy OpenBLAS
  path before falling back to scalar math (`src/sim/search/CombatPVNet.cpp`,
  BLAS initialization; `src/sim/search/CombatDistValueNet.cpp`, BLAS
  initialization). This is not portable across developer environments.

## Relevant code

- `include/combat/BattleContext.h` — `BattleContext`, `Outcome`.
- `src/combat/BattleContext.cpp` — `init`, `executeActions`, `exitBattle`.
- `include/sim/search/Action.h` and `src/sim/search/Action.cpp` — `Action`.
- `src/sim/search/ScumSearchAgent2.cpp` — combat dispatch and action commit.
- `include/sim/search/BattleScumSearcher3.h` and
  `src/sim/search/BattleScumSearcher3.cpp` — particle search.
- `src/sim/search/CombatObservation.cpp` — observation and belief operations.
- `src/sim/search/CombatValueNet.cpp` — canonical features and native value/policy inference.
