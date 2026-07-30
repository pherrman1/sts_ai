# Glossary

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

**BattleContext** — Mutable state for one combat, including combat RNGs,
queues, player, monsters, cards, potions, and `Outcome`
(`include/combat/BattleContext.h`, `BattleContext`).

**bestbench** — `one_combat` mode that evaluates the current whole-run OOC
stack over a seed range and optionally writes per-seed CSV
(`apps/one_combat.cpp`, `bestBench` and `main`).

**Combat observation** — Search-visible combat projection created from a
`BattleContext`; hidden determinizations are represented separately
(`include/sim/search/CombatObservation.h`, `CombatObservation`,
`HiddenBattleState`).

**Counterfactual** — In this repository, a copied run state on which an
alternate `GameAction` is applied before continuation or future-combat scoring
(`apps/one_combat.cpp`, `OocCounterfactualResult`, `FutureFightProbe`, and
next-combat collection code).

**Fair play** — Project evaluation mode selected by `STS_FAIR` that commits one
root move before rebuilding search. Default Searcher2 randomizes draw order and
shuffle/card RNG only; Searcher3 must be enabled separately for its six-stream
particles (`src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair`;
`src/sim/search/BattleScumSearcher2.cpp`, `determinize`).

**GameAction** — Packed 32-bit strategic/run-level action, distinct from a
combat `Action` (`include/sim/search/GameAction.h`, `GameAction`).

**GameContext** — Mutable state for a complete run and its active screen
(`include/game/GameContext.h`, `GameContext`, `ScreenState`).

**Known-RNG** — Non-fair combat path in which search operates from the concrete
battle state and may reuse the tree across committed actions
(`src/sim/search/ScumSearchAgent2.cpp`, `playoutBattle`). Recorded results from
this regime are optimistic relative to hidden-information play.

**Meta arm** — Self-play gate arm intended to contain the run-level value/rest
candidate (`selfplay/loop.sh`, adaptive gate and `meta_trained` promotion
branch). The current candidate server is bypassed by default native OOC, so the
arm is not presently validated.

**Native OOC** — In-process compact tree inference for floor/win strategic
values, enabled by default unless `STS_NATIVE_OOC=0`
(`apps/one_combat.cpp`, `main`, `g_floorNet`, `g_winNet`).

**OOC** — Out of combat; choices represented by `GameAction` while
`GameContext::screenState` is not `BATTLE`
(`src/sim/search/ScumSearchAgent2.cpp`, `playout`,
`stepOutOfCombatPolicy`).

**Particle / determinization** — One sampled assignment of hidden combat state
used to search a possible world (`include/sim/search/CombatObservation.h`,
`HiddenBattleState`, `Belief`; `src/sim/search/BattleScumSearcher3.cpp`,
`applyParticle`).

**Policy prior** — Normalized per-edge preference used by PUCT, computed from
combat action/state features (`src/sim/search/BattleScumSearcher3.cpp`,
`computeEdgePriors`, `selectBestEdgePUCT`). The 14 action features include
hand-authored `Expert` play-order and obtain-weight values
(`src/sim/search/CombatValueNet.cpp`, `combatFillActionFeatures`).

**PUCT** — Search selection formula combining average value with
prior-weighted exploration; the repository default constant is `g_cPuct=2.5`
(`src/sim/search/BattleScumSearcher3.cpp`, `selectBestEdgePUCT`;
`src/sim/search/CombatValueNet.cpp`, `g_cPuct`).

**RICH / rich state** — Repository term for the OOC feature vector emitted by
`vFeatCsv`, currently mirrored as 1,017 raw inputs by the server
(`apps/one_combat.cpp`, `vFeatCsv`; `v_server.py`, raw feature layout).

**Searcher2** — Default combat tree search implementation
(`include/sim/search/BattleScumSearcher2.h`, `BattleScumSearcher2`).

**Searcher3 / ISMCTS** — Opt-in particle combat search with observations cached
in nodes (`include/sim/search/BattleScumSearcher3.h`, `BattleScumSearcher3`;
`src/sim/search/BattleScumSearcher3.cpp`, `step`). Its current
`Belief::update` is a no-op, so “belief” does not imply observation-conditioned
filtering.

**Teacher** — Search or counterfactual process whose outcomes or visits become
training targets. `fightgen`, for example, logs fight outcomes and root visit
distributions through agent callbacks (`apps/one_combat.cpp`, `fightgen`
generation section; `include/sim/search/ScumSearchAgent2.h`, callbacks).
Its combined policy logging is wired for Searcher2, not Searcher3.

**V_floor / V_win / V_combat** — Learned predictions for run progress, run win
probability, and combat outcome/value respectively (`train_value_rich.py`,
top-level trainer; `train_winrate.py`, top-level trainer;
`train_value_combat.py`, top-level trainer).

## Relevant code

- `include/game/GameContext.h` — run vocabulary.
- `include/combat/BattleContext.h` — combat vocabulary.
- `include/sim/search/` — action, observation, search, and model terms.
- `apps/one_combat.cpp` — experiment-mode and OOC terms.
- `selfplay/loop.sh` — self-play/gating terms.
