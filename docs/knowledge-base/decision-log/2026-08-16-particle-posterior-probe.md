# 2026-08-16 — Phase-1b posterior-valid particle sensitivity probe

Implemented the Phase-1b shadow diagnostic only. This is the follow-up to the
Phase-1a draw-order probe recorded the same day.

Phase 1a measured artificial draw-order sensitivity: visible leaf state,
draw-pile multiset, and all six simulator RNG streams held fixed while draw
order was permuted. Phase 1b measures sensitivity among FULL hidden
hypotheses taken from Searcher3's ACTUAL current finite root belief that
remain compatible with the same semantic action history and the same
resulting visible leaf observation (exact intermediate and final
observation/outcome equality). Phase 1b never calls this an exact Bayesian
posterior — validity is relative to Searcher3's finite belief approximation.

No runtime particle-conditioned VNet, no belief changes, no particle-count
change, no Searcher3 action-selection change, and no gameplay promotion were
made. The pre-registered GO/STOP/INCONCLUSIVE decision rule was recorded in
`docs/experiments/ledger-06.md` §175 BEFORE any Phase-1b scientific data
collection.

The §175 v1 full-particle gate was superseded before the designated scientific
run after implementation review identified a confound: full candidate RNG
streams plus draw order plus one rollout measure total random-future variation,
not clean draw-order-conditioned valuation. §176 therefore makes the
controlled draw-order target primary (source RNG streams held fixed, R=4 common
rollouts per compatible draw order) and retains the full-particle target as a
secondary #4-oriented quantity. The primary statistic is equal-source-group
mean/range prevalence; compatible-mass-weighted results are secondary.

Key implementation facts:

- `one_combat particle_posterior_probe`; env `STS_PARTICLE_POSTERIOR_PROBE_FILE`,
  `…_K` (0 = evaluate all unique compatible states), `…_MAX_GROUPS`
  (-1 unlimited / 0 probe-OFF determinism arm / >0 cap).
- `BattleScumSearcher3::step` gains optional per-action semantic checkpoints
  (`g_s3LeafTraceActions`, default off) capturing card identity from the
  pre-action state and actual post-action `CombatObservation` + `Outcome`.
- `applyHiddenStateExact` installs a particle exactly or returns false;
  fallback shuffles are never accepted as compatible worlds.
- Diagnostic exact draw-pile multiset identity uses `FullHiddenCardId`; the
  gameplay CardId-only multiset predicate remains unchanged.
- The smoke sidecar records per-decision Searcher3 root fingerprints: visible
  observation hash, chosen root action bits, and chosen-edge visits. This
  supports action/search-level OFF/ON equality checks rather than only outcome
  equality.
- Source-particle replay is mandatory for exactly-applied source groups
  (`sourceParticleReplayOk` must be 1); `SOURCE_PARTICLE_FALLBACK` groups are
  ineligible, with `rootCarried`/`reuseGeneration` recorded for attribution.
- Files: `include/sim/search/BattleScumSearcher3.h`,
  `src/sim/search/BattleScumSearcher3.cpp`, `apps/one_combat.cpp`,
  `tools/analyze_particle_posterior_probe.py`,
  `tools/seed_guard.sh` (mode registered), `CMakeLists.txt` (self-test),
  `docs/knowledge-base/architecture/combat-search.md`,
  `docs/knowledge-base/operations/environment-variables.md`,
  `docs/experiments/ledger-06.md` §175.
