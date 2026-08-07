# 2026-08-07 — S3 forced-move port (onlyLegalAction in the Searcher3 fair path): promoted shortcut extended to Searcher3 — gate passed, confirmed default ON (0/256 diffs, −8.5% cpu)

## Decision

Extend the promoted forced-action contraction (Phase 5, §120/§121) to the
Searcher3 fair path: `BattleScumSearcher3::onlyLegalAction(Action&)`
(identical live-root canonical enumeration via S3's own
`enumerateActionsForNode`), wired into `ScumSearchAgent2::playoutBattleFair`
'$S3 branch' behind the same `g_forcedMoveSkip` flag (`STS_FORCED_MOVE`,
default ON in the fair path). Non-fair S3 path untouched (persistent
`advanceRoot` tree, same §121 rationale as S2).

## Rationale

**Inference:** the §120/§121 neutrality argument (a single legal action is
forced in every determinization; the fair path builds a fresh searcher per
decision, so skipping the search is decision-neutral) applies to S3's
particle regime identically — forced-move firing is a property of the live
root state, not of the belief. The cpu saving (S2: −16 to −18%) should
transfer. 8-seed local smoke (S3−bc, 256p, fair @1k): **0/8 per-seed
outcome diffs** on won/floor/act/hpEnd/fightsLost/deathCombat/deathEncounter
at cpu 5.43 → 4.55 s/run (−16%), consistent with neutrality.

## Alternatives considered

- Extract a shared free `onlyLegalAction(const BattleContext&)` used by both
  searchers: rejected — S2/S3 enumeration functions operate on different
  Node/Edge types; a shared helper would duplicate or refactor canonical
  enumeration for zero behavioral gain, and S2 is already gated twice.
- Env-gate the S3 port behind `STS_FORCED_MOVE=1` opt-in first: rejected as
  over-cautious — the flag is already default-ON fair-path for S2, and the
  §123 paired gate is the arbiter either way (`STS_FORCED_MOVE=0` is the
  control).

## Evidence

- Code: `BattleScumSearcher3::onlyLegalAction`
  (`include/sim/search/BattleScumSearcher3.h`,
  `src/sim/search/BattleScumSearcher3.cpp`), agent wiring
  (`ScumSearchAgent2.cpp::playoutBattleFair`), env parse unchanged
  (`apps/one_combat.cpp::main`, `STS_FORCED_MOVE`).
- Paired 256-seed gate (EXPERIMENTS.md §123, block 250000–250255, fair,
  S3−bc @3k, 24 threads, GCP): `build/lv2_s3_ctl_256.csv` (default forced
  ON) vs `build/fm3_s3_flat_256.csv` (`STS_FORCED_MOVE=0`) — 0/256 diffs on
  won/floor/act/hpEnd/maxHp/fightsLost/deathCombat/deathEncounter; cpu
  61.85 vs 67.60 s·run (−8.5%).
- Local pre-gate smoke: `build/fm3_s3_flat_8.csv` vs
  `build/fm3_s3_forced_8.csv`, 0/8 diffs at −16%.
- Config: `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=256`, bestbench @3k, asc 0, native OOC, policy PUCT.

## Status

- S2 fair path: unchanged (still default ON, §120/§121).
- S3 fair path: **gate passed — confirmed default ON (EXPERIMENTS.md §123).**
  Paired 256-seed fair S3−bc @3k gate (block 250000–250255, GCP): ctl
  (default forced ON) vs `STS_FORCED_MOVE=0` gives **0/256 per-seed outcome
  diffs** on all 8 outcome columns at cpu 61.85 vs 67.60 s·run
  (**−8.5%**). The port is decision-neutral in the particle regime, matching
  the §120/§121 S2 standard. Note: the cpu saving is smaller than S2's
  −16-18% because the S3 searcher (incl. particle belief) is constructed
  before the check; a pre-check enumeration would recover more cpu but was
  not pursued (small scope, §123).
