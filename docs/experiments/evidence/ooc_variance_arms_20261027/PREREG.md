# #883 phase 3: survival-weighted rollouts and event-keyed streams (pre-registration, 2026-10-27)

Philipp, 2026-10-27 20:37Z (through the coordinator): "go and merge", Phase 3 now, without waiting for #881. Design:
[variance-reduction.md](../../../knowledge-base/research/ooc/variance-reduction.md) (§699).

## Question
For OOC rollout3 sibling differences at today's A20 default, do survival-weighted rollouts (conditional Monte Carlo
on the CTM death draw) and event-keyed random streams cut variance per CPU-second, without changing the estimand?

## Instrument (research, default off; play unchanged)
`STS_OOC_SIBLING_VR_ARMS=base,indep,sw,keyed,swkeyed` with `STS_OOC_SIBLING_VR_REPEATS=R`. For every depth-1 child of
each captured root, a forked child runs R rollout3 repeats per arm. Repeat r of every arm and every child starts from
`seed_seq{searchSeed, decision, leafKey, 4, r}`. `leafKey` is a constant, except under indep, which uses per-leaf
seeds. So the arms are paired by r, and every arm except indep pairs the children too.
- **base:** today's common-seed capture.
- **indep:** per-leaf streams (the control without common random numbers).
- **sw:** each CTM fight of the rollout outside Act 4 is drawn from the CTM conditioned on survival, by rejection.
  The value is multiplied by Π (1 − death), with death taken from the sampler's own `expectation()`, which is
  1 − runtime survival, the same probability `sample()` uses. Act-4 fights and fights without a CTM expectation keep
  the sampled death.
- **keyed:** each rollout step draws from a fresh stream keyed by (act, floor, screen, kind, occurrence) under the
  repeat's base draw.
- **swkeyed:** both.

## Roots (no new seeds)
The first 8 seeds of §683 (111374100–111374107, used), replayed at this commit with today's A20 default (§695's
replay environment) plus `STS_OOC_MCTS_SCREENS=map,rewards`, so OOC search runs at reward and map roots. Each game
stops at its first Act-4 state. Searching reward roots changes play against §683, so these replays are new games on
used seeds; the arms themselves run in forked children and do not change play (smoke below). Every searched root is
captured (depth 1, at most 16 children); R = 128.

## Measures (analyze.py)
- **Target:** var(mean over R of v_i − v_j) for every child pair of a root, pooled by root (sum over pairs). The
  ratio to base comes with a root-bootstrap 95% CI, by screen (rewards primary, map secondary).
- **Work ratio:** variance ratio × CPU ratio (cpuSeconds per arm), i.e. variance at equal CPU.
- **Bias check (each arm against base, per child):** mean difference over r, its z, the fraction of |z| > 2, and the
  pooled mean difference clustered by root.

## Decision (rewards roots; map reported the same way)
- **USEFUL:** work ratio ≤ 0.5 against base, with no bias flag (root-clustered pooled mean difference within ±2 SE,
  and the fraction of |z| > 2 at most 8%).
- **NOT_USEFUL:** work ratio ≥ 0.8.
- **WEAK:** in between.
- A bias flag on any arm makes that arm INVALID, whatever its variance.
- A useful arm becomes a follow-up proposal only (labels, campfire price, card-rule search). There is no default
  change, and any play use needs its own A/B.

## Smoke (before the run)
1. Seed 111374100 with `STS_STOP_AFTER_ACT=1`, R = 8, capture with arms against capture without arms. The policy JSONL
   and trace must be identical apart from timing fields.
2. Every arm row valid.

## Cost
~85 roots per game × ~6 children × 128 × 5 arms ≈ 330k rollouts per game at ~8 ms each, ≈ 45 CPU-min per game plus
the game itself. 8 games ≈ 8–10 core-h on this 4-CPU container (~2.5 h wall).
