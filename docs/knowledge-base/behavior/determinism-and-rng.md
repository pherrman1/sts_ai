# Determinism and RNG

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Run RNG ownership

`GameContext` stores separate RNG streams for AI choices, cards, events,
merchants, monsters, potions, relics, shuffling, treasure, and other simulator
domains (`include/game/GameContext.h`, `GameContext` hidden-from-player
section). `GameContext::GameContext` seeds and consumes those streams while
initializing the run (`src/game/GameContext.cpp`,
`GameContext::GameContext`, `initRelics`, `initPlayer`, `generateMonsters`).

`BattleContext` carries the combat-relevant subset: `aiRng`, `cardRandomRng`,
`miscRng`, `monsterHpRng`, `potionRng`, and `shuffleRng`
(`include/combat/BattleContext.h`, `BattleContext`). `BattleContext::init`
initializes AI, monster-HP, shuffle, and card-random RNGs from the same
`Random(gc.seed + gc.floorNum)` value, while copying `miscRng` and `potionRng`
from the run. `BattleContext::exitBattle` copies all six resulting states back
(`src/combat/BattleContext.cpp`, `init`, `exitBattle`). Search
determinizations mutate battle copies, not the committed live battle.

## Visible versus hidden combat state

Searcher3 separates `CombatObservation` from `HiddenBattleState`.
`CombatObservation::fromBattleContext` captures the state it treats as visible;
`visibleHash` is only a partial hash. `HiddenBattleState::sampleParticles`
generates sampled determinizations used by `Belief`
(`include/sim/search/CombatObservation.h`, `CombatObservation`,
`HiddenBattleState`, `Belief`; `src/sim/search/CombatObservation.cpp`, named
methods).

`BattleScumSearcher3::step` samples a particle, applies it to a copied root
state, then searches that world. `ScumSearchAgent2::playoutBattleFair` commits
only the most-visited root move before observing and searching again
(`src/sim/search/BattleScumSearcher3.cpp`, `step`, `applyParticle`;
`src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair`). This is the
implementation basis for Searcher3 fair mode. `Belief::update` is a no-op and
`Belief::sample` ignores weights, so particles are not conditioned on observed
draws (`src/sim/search/CombatObservation.cpp`, named methods).

By default `STS_FAIR=1` still uses Searcher2. Its `determinize` shuffles the
draw pile and replaces only shuffle/card-random RNG; AI, misc, monster-HP, and
potion RNG remain concrete. Fair play is a repository regime label, not a
verified complete hidden-information boundary
(`src/sim/search/BattleScumSearcher2.cpp`, `determinize`;
`src/sim/search/BattleScumSearcher3.cpp`, `g_useSearcher3`).

Known-RNG `ScumSearchAgent2::playoutBattle` may reuse a search tree across
actions via `advanceRoot`, while the fair path rebuilds per observed decision
(`src/sim/search/ScumSearchAgent2.cpp`, `playoutBattle` and
`playoutBattleFair`; `src/sim/search/BattleScumSearcher2.cpp`,
`BattleScumSearcher2::advanceRoot`; `src/sim/search/BattleScumSearcher3.cpp`,
`BattleScumSearcher3::advanceRoot`).

## Copy safety

`GameContext::map` is shared ownership (`include/game/GameContext.h`,
`GameContext::map`). A counterfactual copy therefore shares its `Map` until the
experiment code explicitly detaches it; branches that will mutate map state
must clone the map first (`apps/one_combat.cpp`, counterfactual map-detachment
code). `ScreenStateInfo` gives inactive-screen fields deterministic sentinel
values specifically to avoid stack-reuse-dependent copies
(`include/game/GameContext.h`, `ScreenStateInfo`).

`BattleContext::init` explicitly resets nested transient structures before
copying run data (`src/combat/BattleContext.cpp`, `BattleContext::init`).
`EXPERIMENTS.md` entry 66f attributes a repaired repeated-seed divergence to
this reset. The implementation is verified; the historical causal claim is
experiment-log provenance.

## Current determinism uncertainties

- **Discrepancy:** Searcher3's comment promises composite seeding from
  `agentSeed`, `visibleHash`, and `decisionIndex`, but construction consumes
  both configurable members at their default zero values. The agent assigns
  `s3.agentSeed = bc.seed` only after construction, and no code assigns
  `decisionIndex`
  (`src/sim/search/BattleScumSearcher3.cpp`, constructor;
  `src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair` and
  `playoutBattle`; `include/sim/search/BattleScumSearcher3.h`, member defaults).
- **Discrepancy:** `CombatObservation::operator==` omits draw-pile contents and
  several fields included by `visibleHash`; the hash itself omits other stored
  fields. Equal observations can therefore hash differently, and distinct
  observations can share the intended identity (`src/sim/search/CombatObservation.cpp`,
  `operator==`, `visibleHash`).
- **Unverified:** `EXPERIMENTS.md` entries 66e and 66j report repeated
  multi-thread fair-play runs that were not bit-identical. No current automated
  reproducibility test covers whole-run CSV equality (`CMakeLists.txt`, absence
  of `add_test`; `apps/one_combat.cpp`, `bestBench`).
- **Open question:** whether remaining divergence comes only from search RNG
  initialization, OpenMP scheduling, shared mutable globals, or multiple
  causes. The repository contains no closed investigation proving one cause.

## Reproducibility checklist

Record the game seed block, `STS_FAIR`, `STS_SEARCHER3`, simulation count,
ascension, model paths and load messages, thread counts, executable/model
hashes, and all policy flags. The self-play gate hashes its binary, models, and
evaluation configuration for baseline-cache identity (`selfplay/loop.sh`,
baseline-cache key construction).

That cache key is incomplete for current native OOC: it hashes the loop's
`current/v_win.json` but not the fixed `build/v_rich_trees.txt` or
`build/v_win_trees.txt` that `one_combat` actually loads. If server-backed OOC
is restored, it also does not hash `v_server.py` or Python dependencies.
Combined with unresolved repeated-seed divergence, the comment that baseline
outcomes are deterministic is an assumption, not a verified invariant
(`selfplay/loop.sh`, `baseline_cache_key`; `apps/one_combat.cpp`, native OOC
startup).

## Relevant code

- `include/game/GameContext.h` — run RNG streams, `ScreenStateInfo`, shared map.
- `src/game/GameContext.cpp` — run construction and RNG-consuming transitions.
- `include/combat/BattleContext.h` and `src/combat/BattleContext.cpp` — combat RNG boundary.
- `include/sim/search/CombatObservation.h` and
  `src/sim/search/CombatObservation.cpp` — visible/hidden split.
- `src/sim/search/BattleScumSearcher3.cpp` — particle application and RNG seed.
- `src/sim/search/ScumSearchAgent2.cpp` — fair versus known-RNG execution.
- `selfplay/loop.sh` — evaluation cache provenance.
