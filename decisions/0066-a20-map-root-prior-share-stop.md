# ADR-0066: At A20, a searched map root stops early once the prior argmax holds 90% of the visits

Date: 2026-11-04
Status: accepted

Adds an early stop to [ADR-0065](0065-a20-map-root-sims-1024.md)'s 1,024-simulation A20 map roots.

## Context

#942 added `STS_OOC_MCTS_PRIOR_SHARE_STOP=H` (default off): a full-budget map root checks after 128, 256 and 512
simulations and stops once the most-visited action is the prior argmax (ties: lowest id) and holds at least `H` of the
root visits. It is the native form of the offline rule S_prior (`map_root_maxq_count_20261101/budget_stop.py`). The
pre-registered non-inferiority SPRT (§753: d0 −1.5 pp, d1 0, α = β = 0.05, ADR-0064 control reuse of §741 B / §727 A
over 1,536 seeds) gave **NOT_WORSE** for H = 0.9. Heart kills were 25.65% vs 25.72% (−0.07 pp [−0.59, +0.46]) at
0.38x the map-root simulations. Only 49 of 1,536 games diverge; on those, the kills were 19 vs 20. The run used
85bf1ba0, from before #957/#970/#976.

Philipp decided on 2026-11-04 (08:36 CET): "Yes mach es Standard".

## Decision

- With `STS_OOC_MCTS_PRIOR_SHARE_STOP` unset, an ADR-0061 map root (A20, heart1 prior, outside the live advisor,
  `STS_OOC_MCTS_SCREENS` unset, `STS_OOC_MCTS_FULL_BUDGET_FRACTION` set) uses the prior-share stop with H = 0.9
  (`kA20PriorShareStop`) at the checkpoints 128, 256 and 512 below its budget. This is exactly §753's arm C.
- `STS_OOC_MCTS_PRIOR_SHARE_STOP=0` restores the full map-root budget. An explicit `H` keeps its old meaning: every
  full-budget map root of the run uses that `H`.
- The default does not depend on `STS_OOC_MCTS_FULL_ROOT_SIMS`; it still stops at 128/256/512 when that flag sets
  another budget.
- Below A20, with `STS_OOC_MCTS_SCREENS` set, without the fraction, in the live advisor, in offline scoring and for
  imagined decisions, nothing changes. The stop never acts under a Gumbel root, Q selection or root-lock observation.
- The startup banner prints `prior_share_stop_a20_default=0.900000`. The OOC provenance JSON records
  `"priorShareStopA20Default":0.900000`. Policy rows carry `root.priorShareStop` and `root.earlyStopPriorShare`, and
  run profiles `early_stop_prior_share`, at every root where a share applies.

## Consequences

- Play changes at the few map roots where the stop picks a different move than the 1,024 tree (§753: 49 of 1,536
  games). Map-root simulations drop to about 0.38x of ADR-0065's. End to end the saving is smaller, because combat
  takes most of the CPU; the §753 diverging games suggest roughly 0.6x wall per game (indicative, other machines).
- AZ policy targets at A20 map roots now come from trees that may stop at 128/256/512 simulations. Those trees are
  the prior-confirming cases, so the visit target sits close to the prior there.
- Comparability: runs from before this ADR at A20 are reproduced with `STS_OOC_MCTS_PRIOR_SHARE_STOP=0` (and, for
  before ADR-0065, `STS_OOC_MCTS_FULL_ROOT_SIMS=0` as well). Freeze files must record the flag.
