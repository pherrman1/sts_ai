# Investigations

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

This directory is for reproducible, unresolved technical investigations. An
investigation is evidence collection, not a decision or a speculative design.

## Candidate investigations from the initial assessment

- Searcher3 composite seed contract: the constructor seeds before the caller
  assigns `agentSeed`, and no caller assigns `decisionIndex`
  (`src/sim/search/BattleScumSearcher3.cpp`,
  `BattleScumSearcher3::BattleScumSearcher3`;
  `src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair` and
  `playoutBattle`).
- PVNet-only priors: node expansion gates `computeEdgePriors` on the policy-net
  flag while PUCT activation also recognizes PVNet
  (`src/sim/search/BattleScumSearcher3.cpp`, `step`,
  `selectBestEdgePUCT`, `computeEdgePriors`).
- Whole-run fair-play reproducibility: recorded multi-thread reruns differ, but
  no automated repeated-seed CSV equality test exists (`EXPERIMENTS.md`,
  entries 66e and 66j; `apps/one_combat.cpp`, `bestBench`;
  `CMakeLists.txt`, absence of registered tests).
- Result CSV consumer drift: `paired_analysis.py` `load` does not match
  `apps/one_combat.cpp` `bestBench` column order.
- Self-play meta-arm bypass: the loop starts a candidate V_win/rest server but
  leaves native OOC enabled, so fixed native artifacts own the decisions
  (`selfplay/loop.sh`, policy env and `start_server`;
  `apps/one_combat.cpp`, native startup and rest queries).
- Combat observation identity/belief: equality and hash cover different field
  sets, and `Belief::update` is a no-op
  (`src/sim/search/CombatObservation.cpp`, `operator==`, `visibleHash`,
  `Belief::update`).
- Self-play bootstrap: `state.env` exists while `current/` is absent, the loop
  consumes `./one_combat.elf`, and its first-run model sources are absent.
- Clean-clone build reproducibility: `.gitmodules` and `CMakeLists.txt`
  reference json/pybind11 directories not represented as gitlinks in this
  checkout, and current docs reference an undefined `libsts.a` target.

These are candidates, not completed diagnoses. Create a dedicated page only
when there is a minimal reproduction, captured observations, and an explicit
next discriminating check.

## Required record format

Each investigation should include status, `Last verified`, symptom, scope,
exact reproduction, expected/observed results, evidence, hypotheses labelled
**Inference**, eliminated hypotheses, current blocker or next check, and a
`Relevant code` section. Close it with the fixing commit/test or mark it
obsolete if the reproduction disappears.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp` — current search/RNG candidates.
- `src/sim/search/ScumSearchAgent2.cpp` — Searcher3 construction and fair execution.
- `apps/one_combat.cpp` — reproducibility and CSV producer paths.
- `paired_analysis.py` — current CSV consumer.
- `CMakeLists.txt` and `.gitmodules` — bootstrap discrepancy.
