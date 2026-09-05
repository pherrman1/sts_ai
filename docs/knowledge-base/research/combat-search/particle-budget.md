# Searcher3 particle budget

Last verified: 2026-08-11.

## Purpose / research question

How many particles does Searcher3 need? Is the particle budget a free parameter
or does it trade off against simulation count?

## Current conclusion

**64 particles is the deployed default.** 128 particles is promising (direction
positive, monotonic collapse reduction) but not confirmed for promotion.
Utilization remains high at 128–256 particles at 1,000 simulations, so there
is no immediate evidence of starvation at the efficient operating point.

Key evidence:

- Particle count was flat in the §115 grid: 16, 64, and 256 particles produced
  similar win rates at fixed simulation budgets.
- The 2026-08-10 sweep with filtering ON showed monotonic collapse reduction
  (15%→10%) but non-monotonic win rates (64p: 9/32, 128p: 14/32, 256p: 11/32,
  512p: 11/32).
- The 32-seed 128p extension showed 18/64 vs 24/64 wins for 64p vs 128p
  (direction positive, noisy).
- No particle×simulation interaction arm has been run.

**Do not claim 128 particles as the deployed default.** It remains experimental.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-08-05 | [§115 particle×sims grid](../../../../docs/experiments/ledger-04.md) | Flat in particles (16/64/256) at 1k/3k |
| 2026-08-10 | [Particle-count sweep](../../../../docs/experiments/ledger-01.md) (search for "particle-count sweep") | 128p directional positive, 256p/512p no further gain; collapse monotonic |
| 2026-08-10 | Decision: particle-count sweep | 128p promising but not confirmed; keep 64p default |

## Rejected / falsified approaches

- **256 particles as belief-capacity fix** — E1 arm of §115 showed belief ON at 256 particles
  still −6.2pp vs belief OFF at 64 particles.
- **512 particles for further collapse reduction** — did not improve gameplay over 128p.

## Relationships

- [belief-state.md](belief-state.md) — collapse rate is strongly particle-count-dependent
- [searcher3.md](searcher3.md) — `STS_S3_PARTICLES=64` is the §124 confirmed config
- [leaf-evaluation.md](leaf-evaluation.md) — particle worlds affect leaf value relevance

## Current implementation

`STS_S3_PARTICLES=N` (default 64). One particle is sampled per MCTS simulation.
Particle construction scales with count; per-simulation determinization uses one
sampled world regardless of total particles.

## Open questions

- Would a 128p confirmation gate on a full 256-seed block be significant?
- Does the particle×simulation interaction matter (e.g., 128p × 2,000 sims)?
- Would 64p remain optimal under the live-valid + forced-move + VNet default stack?
