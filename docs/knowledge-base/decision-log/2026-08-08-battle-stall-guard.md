# 2026-08-08 — Stall-battle guard in the battle loops

Date: 2026-08-08
Session/task: Datagen seed 300865 never completed — root-caused the S3 fair battle loop stalling forever.

## Decision

All four `while (bc.outcome == Outcome::UNDECIDED)` battle loops in
`ScumSearchAgent2.cpp` (`playoutBattleFair` S3/S2, `playoutBattle` S3/S2) now
have a `kMaxBattleDecisions = 1000` stall guard: an exceeded battle is
treated as `PLAYER_LOSS` with a `[battle-stall]` warning. The guard counter is
separate from `decisionIdx` (which seeds the per-decision searcher), so
default search behavior is unchanged.

## Rationale

StS has no stall timer, so a fight can legitimately last forever; the S3
search plays such fights defensively (block/heal more than the boss damages)
and never finishes them. Seed 300865 reaches the act-1 boss (encounter 31)
where the cheap eval policy dies instantly but the search stalls eternally —
single core, zero rows written (rows buffer until seed end), no deadlock,
busy backtraces. ~1/1000 seeds hit a stallable fight; 999/1000 completed
normally. Normal battles finish in well under 100 decisions, so 1000 is a
10×+ safety margin.

## Alternatives considered

- No guard (status quo) — rejected: one stall seed hangs a whole datagen chunk.
- Lower cap — rejected: boss fights with long stalls could legitimately reach
  hundreds of decisions; 1000 keeps the margin safe without tripping on real
  fights.

## Evidence

- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`/`playoutBattle` +
  `kMaxBattleDecisions`.
- EXPERIMENTS.md §140: seed 300865 before (never completes, 30+ min) vs after
  (3 stall warnings, 245s local / 590s GCP, 746 rows, rc=0); chunk 2 now
  500/500 seeds (273,518 rows).

## Status and follow-up

- Implemented and verified. Chunk 3 of the 5.7.3 datagen runs with the guard.
- Open: whether a stallable battle should be a LOSS or something else (a
  human would eventually win or lose by decking out) — the conservative LOSS
  stands until evidence suggests otherwise.
