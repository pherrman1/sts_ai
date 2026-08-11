# Fightrep harness: isolated Act-3 boss fight replay

Date: 2026-08-11

## Decision

Add a fight-start snapshot/replay harness for Act-3 (floor-50) boss fights so
the recorded 14 floor-50 losses can be re-searched at other particle counts /
sim budgets without re-running the full run.

- Capture: `STS_FIGHTREP_CAPTURE_DIR=<dir>` makes `runFullRunOOC` serialize
  each Act-3 boss fight's STARTING `BattleContext` to `fight_<seed>.bin`
  (raw `serializeBattleContext` blob) and write `fight_<seed>.csv`
  (seed,encounter,floor,won,hpEnd,turns) after the fight. One file per seed so
  parallel capture processes are race-free.
- Replay: new mode `one_combat fightrep CAPTURE_DIR OUTFILE PARTICLES SIMS
  [NFIGHTS]` re-plays the isolated fights across a (particles x sims) grid
  with the recorded fair-S3 stack (forced belief=off chain=off live-valid=on)
  and writes seed,encounter,floor,particles,sims,won,hpEnd,turns.
- `tools/seed_guard.sh` registers `fightrep` and caps the replay as
  NFIGHTS x |PARTICLES| x |SIMS| replay cells (128 automated ceiling).

## Rationale

The 14 floor-50 losses come from the A0 1k/128-seed rerun
(`build/rerun_2026-08-10_a0_gates_1k_128.csv`). Replaying only the isolated
boss fight is far cheaper than a full run (~8 s vs ~170-450 s per seed) and
isolates the search-budget question. `BattleContextBinary` already round-trips
the visible state + all six RNG streams + `bc.seed`; the S3 searcher seeds its
RNG from `bc.seed ^ obsHash ^ decisionIdx`, so a captured fight-start replays
deterministically.

## Evidence

- Single-seed capture smoke (seed 126721) reproduced the historical row
  (floor 50, encounter 54=Time Eater, loss, hpEnd 0).
- Fidelity gate PASS: replay of the captured 126721 fight at 64 particles /
  1000 sims (boss x3 = 3000/decision, matching the recorded run) reproduced
  the capture-time loss exactly (won=0, hpEnd=0, turns 6).
- `tools/seed_guard.sh guard-only ... fightrep ... 64,128 500,1000 64` rejected
  (256 cells > 128); the 14-fight grid passed.

## Status

Implementation + single-seed fidelity verified on the local build. The 14-seed
capture set and the particles x sims sweep are pending (9/14 fights captured
locally before the session was paused; remainder continue on another machine).

## Open question

Local HEAD differs from the GCP historical commit `5959e4c`, so replay
outcomes at the recorded config should be compared with the historical per-seed
rows when possible; the hard fidelity gate is replay == capture-time outcome.
