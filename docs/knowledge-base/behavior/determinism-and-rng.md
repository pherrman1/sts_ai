# Determinism and RNG

Last verified: 2026-07-31 against commit `67320b3` and the current working tree.

## Purpose

Document RNG ownership, project-fair determinization, copy boundaries, and the
known gaps that prevent claims of complete hidden-information modeling or
bit-reproducible whole-run evaluation.

## Current implementation

`GameContext` owns separate RNG streams for AI choices, cards, events,
merchants, monsters, potions, relics, shuffling, treasure, and other domains
(`include/game/GameContext.h::GameContext`). `BattleContext` carries six
combat-relevant streams: AI, card-random, misc, monster-HP, potion, and shuffle
(`include/combat/BattleContext.h::BattleContext`).

`BattleContext::init` initializes/copies combat RNG state from `GameContext`;
`BattleContext::exitBattle` copies resulting stream states back
(`src/combat/BattleContext.cpp::init`, `exitBattle`). Search operates on battle
copies, while the selected action is committed to the live battle.

`STS_FAIR=1` calls `ScumSearchAgent2::playoutBattleFair`. With default
Searcher2, each simulation shuffles the draw pile and replaces only shuffle and
card-random RNG. With `STS_SEARCHER3=1`, each sampled `HiddenBattleState`
contains all six seed pairs and a draw order
(`src/sim/search/BattleScumSearcher2.cpp::determinize`;
`src/sim/search/BattleScumSearcher3.cpp::applyParticle`). Searcher3 samples and
applies particle RNG seeds even when `STS_FAIR` is off; its non-fair agent path
reuses the tree. Both fair paths commit one root action and create a new
searcher for the next observed decision.

## Important data flow

1. Run RNG state enters `BattleContext::init`.
2. A fair search copies the root battle for each simulation.
3. Searcher2 partially determinizes the copy; Searcher3 applies a sampled
   particle.
4. Search explores copied worlds and chooses a root move.
5. The agent validates that move against the live battle and applies it if
   valid; Searcher3 filters for live-valid root edges during selection.
6. At combat end, six stream states return to `GameContext`.

Searcher3 intends to seed its `std::mt19937_64` from visible observation,
`agentSeed`, and `decisionIndex`. The constructor performs that calculation
before callers assign `agentSeed`, while `decisionIndex` is never assigned.
Current effective construction therefore uses the visible hash plus default-zero
members (`BattleScumSearcher3::BattleScumSearcher3`;
`ScumSearchAgent2::playoutBattleFair`).

## Invariants and assumptions

- Project-fair and known-RNG results are different regimes.
- “Fair” is a repository mode label, not proof that all player-hidden state is
  modeled.
- Search determinizations mutate copies, not the committed live battle.
- A copied `GameContext` shares `map`; detach before counterfactual mutation.
- Per-seed benchmark CSVs must be aligned by seed because parallel completion
  order is nondeterministic.
- Reproducibility records include revision, seed block, simulation count,
  ascension, searcher, all `STS_*` behavior flags, thread count, model paths and
  hashes, and observed load messages.

## Known limitations

- Searcher2 leaves four combat RNG streams concrete under `STS_FAIR=1`.
- Searcher3's stored `HiddenBattleState::drawPileOrder` is never applied;
  `applyParticle` shuffles the copied pile independently with the searcher RNG.
- `Belief::update` is a no-op and `Belief::sample` samples uniformly, so
  Searcher3 particles are not conditioned on observed draws
  (`src/sim/search/CombatObservation.cpp`).
- `CombatObservation::operator==` and `visibleHash` cover different field sets.
  Equal observations can hash differently and stored distinctions can be
  omitted from the intended identity.
- Historical repeated fair multi-thread runs were not bit-identical
  (`EXPERIMENTS.md` entries 66e, 66j). No automated equality test exists.
- The self-play baseline cache omits fixed native floor/win artifacts from its
  key and assumes deterministic outcomes without a current proof.
- `ScreenStateInfo` sentinel initialization and `BattleContext::init` resets
  reduce stale-copy behavior but do not establish whole-run determinism.

## Open questions

- Which hidden variables belong in the project-fair model for each searcher?
- What equality/hash contract should define a combat observation?
- Should Searcher3 constructor parameters make agent seed and decision index
  explicit and immutable?
- Is remaining replay divergence caused by OpenMP scheduling, shared globals,
  search RNG construction, or multiple factors?

## Relevant code

- `include/game/GameContext.h::GameContext`, `ScreenStateInfo`
- `src/game/GameContext.cpp::GameContext`
- `include/combat/BattleContext.h::BattleContext`
- `src/combat/BattleContext.cpp::init`, `exitBattle`
- `src/sim/search/BattleScumSearcher2.cpp::determinize`
- `include/sim/search/CombatObservation.h::CombatObservation`,
  `HiddenBattleState`, `Belief`
- `src/sim/search/CombatObservation.cpp::visibleHash`, `operator==`,
  `Belief::update`, `sample`
- `src/sim/search/BattleScumSearcher3.cpp::BattleScumSearcher3`, `applyParticle`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`
- `selfplay/loop.sh::baseline_cache_key`
