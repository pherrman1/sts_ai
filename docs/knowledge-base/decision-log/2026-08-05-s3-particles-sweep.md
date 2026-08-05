# 2026-08-05 — S3 particle × sims sweep: S3−belief−chain promoted (60.2% @3k / 57.4% @1k)

**Date:** 2026-08-05. **Task:** sweep particle count × sim budget for the §106
winning S3 variants and confirm on the 256-seed block; decide promotion.
Benchmarked in `EXPERIMENTS.md` §107.

## Decisions

1. **S3−belief−chain is the new recommended combat search** (supersedes
   S2@3k from §99). On the same 256 paired seeds (126700–126955) against
   the recorded 45.3% reference: 3k sims/256 particles = **60.2%
   (+14.8pp, CI [+7.9,+21.8] excluding zero)**, and the compute-efficient
   point 1k sims/64 particles = **57.4% (+12.1pp, CI [+4.9,+19.3])** at
   3.1× less compute (9.8 vs 31.3 cpu-sec/run). Both CIs exclude zero —
   the pre-registered promotion criterion is met.
2. **Operating point: 3k stays the win-rate point; 1k is the deployment
   point.** E2 (4k) adds only +1.6pp vs 3k (noise, §107) — same flattening
   as S2 (§99). The 1k point captures most of the gain at a third of the
   cost; which to run is a compute-budget call.
3. **Particle count is a flat knob: keep 256 (free).** 16/64/256 are within
   noise at every sims×variant cell. No particle-count sweep is needed
   again; `STS_S3_PARTICLES` stays for provenance.
4. **Belief-capacity hypothesis closed.** E1 (belief ON @256 particles @3k)
   = 50.8%, still −6.2pp vs belief-off at the same count and 33% slower —
   the §106 belief harm is design-level, not a 64-particle limit. The
   belief line stays closed.
5. **Promotion is configuration-only, not a code default.** S2 remains the
   binary default; the recommended stack (Searcher3 + `STS_S3_BELIEF=0`
   `STS_S3_CHAIN=0` + V4 gate stack) is opt-in via env, same as the §99
   stack was. `current-baselines.md` gets the new row.

## Rationale

- The both-variant at 3k clusters at 59.4–60.9% vs the anchor 57.8% (A2)
  — chain-off compounds belief-off directionally at every sims level
  (**Inference**, from the grid's consistent +1..+3pp delta).
- Sims matter more than particles in this regime: 1k→3k ~+2-3pp, particle
  count ~0pp; 3k→4k ~+1.6pp (noise). The fair curve's flatness past 3k
  (§99) holds for S3−belief−chain too (**Inference**).
- All labels per the contract: the two promotion CIs are significant; grid
  point-to-point deltas at n=128 are within noise.

## Alternatives considered

- **Promote only the 3k win point** — rejected: the 1k point has an
  excluding-zero CI too and is the economically relevant deployment
  config; both are recorded as the frontier, pairing reference chosen by
  budget.
- **Sweep belief-ON at more particle counts** (512+) — rejected after E1
  closed the capacity hypothesis; belief stays off.
- **4k as the operating point** — rejected: E2's +1.6pp vs 3k is noise at
  1.4× the cost (41.6 vs 29.0 cpu-sec/run).

## Evidence

- `EXPERIMENTS.md` §107 (full grid, batch-2 table, CIs, artifacts).
- `build/pt_sweep_*_128.csv`, `build/pt2_*.csv`; server logs
  `/tmp/s3sweep.log`, `/tmp/s3sweep2.log` on `sts-test`;
  `run_s3_particles_sweep.sh`, `run_s3_particles_sweep2.sh`.
- Code: `apps/one_combat.cpp::main` (`STS_S3_PARTICLES`),
  `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`/`playoutBattle`
  (construction sites), `include/sim/search/BattleScumSearcher3.h`
  (`g_s3Particles`).

## Status and follow-up

- **Closed as promoted.** Baseline table updated (new recommended row;
  §99 row demoted to previous recommended).
- **Cross-session caveats (2026-08-05 code review):** the V4 token net used by
  the gate stack is flagged for a training bug (issue 36, tok glob stats
  columns 44–49; retrain GPU-gated, pending) — the promotion and every
  paired delta here are bug-identical on both sides and stand until the
  retrained gate stack re-pairs. §106's A0/A1 and A3/A5 claims were
  re-verified by the review with clean re-runs and corrected live/CRN
  semantics (issues 41/42/46); the `run_s3_*.sh` scripts now truncate per
  arm against the `bestbench` append trap, and all §107 CSVs were verified
  seed-unique.
- Follow-ups if the line continues: datagen under S3−belief−chain (its
  labels differ from S2-fair data — §98-era policy/visit targets were
  S2-produced); the 1k point for the self-play loop's compute-constrained
  gates; revisit the belief with a much larger particle count only if a new
  mechanism (e.g., observation-conditioned priors) is proposed.
