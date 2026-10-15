# Issue 58: Searcher3 belief collapse admitted "broken" and default ON

- **Status:** closed (2026-08-10)
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/sim/search/BattleScumSearcher3.cpp:31-37`

## Symptom

`g_s3InternalBeliefUpdate = true` with the comment "Default 1 reproduces
historical (broken) behavior where the root belief is destroyed within ~60
simulations and all subsequent sampling is uniform." No resampling/rebirth
exists; `Belief::sample` serves uniform fallback over a stale zeroed set.
The fair path additionally carries a stale belief across decisions with no
boundary update and a false comment at `ScumSearchAgent2.cpp:464-467`.

## Evidence

- `BattleScumSearcher3.cpp:31-37`: explicit admission in code.
- `CombatObservation.cpp:346-356`: `Belief::update` zeros mismatched particles.
- `CombatObservation.cpp:358-376`: `Belief::sample` uniform fallback.
- `BattleScumSearcher3.cpp:229-259`: `applyParticleImpl` fallback shuffles
  with searcher rng, guaranteeing zeroing at next update.
- `ScumSearchAgent2.cpp:464-468`: stale comment about fair path.

## Why it matters

The Searcher3 hidden-information model is advertised as particle ISMCTS but
collapses to uniform within ~60 sims. This is a core soundness issue for the
fair-play path.

## Candidate fix directions

- Disable `g_s3InternalBeliefUpdate` by default, or implement resampling.
- Fix the comment in ScumSearchAgent2.cpp.
- Document the limitation clearly in KB.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp:31-37`, `229-259`
- `src/sim/search/CombatObservation.cpp:346-376`
- `src/sim/search/ScumSearchAgent2.cpp:464-468`
