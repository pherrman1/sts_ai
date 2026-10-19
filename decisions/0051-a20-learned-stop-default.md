# ADR-0051: A20 whole runs default to learned Silver stopping with the retrained A20 stop model

Date: 2026-10-18
Status: accepted

Amends: [ADR-0026](0026-learned-silver-stopping-default.md), which made learned stopping with model
`gbt-770201c31f7b` the default only for `run`/`bestbench`/`reprobench` calls without a sims argument.

## Context

A20 campaigns pass an explicit sims argument (normally 10000), so before this ADR they played flat Silver and the
ADR-0026 default never reached them.

- §538 (PR #674, `docs/experiments/evidence/silver_learnstop_g7f_20261018/`): 512 A20 seeds on the current stack
  (student_sel OOC, g7f_E root table and prior). Learned stop (L, model `gbt-770201c31f7b`) vs flat 10k (F10): Act-4
  reach +3.3 pp [−0.6, +7.3], NON_INFERIOR, at 0.49x CPU. Heart kills L 79, F10 70, flat 2.5k 60. That arm set
  `STS_SILVER_EXACT_ROOT_BUDGETS=1`.
- The stop model `gbt-770201c31f7b` was trained on 160 A0 runs of the V4 stack (§372).
- §543 (PR #678, `docs/experiments/evidence/silver_stoptrace_a20_20261018/`): stop traces from 512 A20 seeds of the
  F10 configuration. A model retrained on 384 of them (`gbt-0cac7cc64364`) was compared with the old model on the
  other 128, at thresholds whose disagreement is at most the old model's out-of-fold disagreement. Saving 58.1% vs 56.2% (+1.9 pp
  [+1.7, +2.0]), disagreement with the 10k action 0.68% vs 0.71%. Result RETRAIN_BETTER.

On 2026-10-18 at 21:44Z Philipp asked to "make learned stoping the default for a20, swpaw the new model in".

## Decision

- `STS_SILVER_LEARNED_STOP_MODEL` selects the compiled stop model by id. Unset selects the A20 model
  `gbt-0cac7cc64364` (threshold 0.032271, `src/sim/search/NativeSilverStopModelA20.cpp`) for every learned-stop
  search at every ascension. `gbt-770201c31f7b` selects the ADR-0026 model (`NativeSilverStopModelA0.cpp`), and any
  other value is refused.
- `run`, `bestbench` and `reprobench` at ascension 20 (argv[4], default 20) default to learned stopping even when a
  sims argument is given. The sims argument is then not used as the budget, and the program prints a line saying so.
  An adaptive knob, `STS_SILVER_LEARNED_STOP`, or `STS_SILVER_STOP_TRACE` still opts out as under ADR-0026.
- At A20 with a sims argument, `STS_SILVER_LEARNED_STOP=0` restores flat Silver at that budget. Without a sims
  argument it keeps #199 adaptive, as under ADR-0026.
- Other ascensions with a sims argument keep flat Silver. Imagined OOC fights keep their own flat budget override.
- Like ADR-0026, the default does not set `STS_SILVER_EXACT_ROOT_BUDGETS`, so one-action roots stay unsearched.

## Consequences

- Every A20 whole run with the default flags plays differently and uses about half the Silver CPU. Comparisons with
  earlier A20 campaigns need `STS_SILVER_LEARNED_STOP=0`. Comparisons with earlier learned-stop runs need
  `STS_SILVER_LEARNED_STOP_MODEL=gbt-770201c31f7b`.
- CTM learned-stop teachers that pin `gbt-770201c31f7b` load only with `STS_SILVER_LEARNED_STOP_MODEL=gbt-770201c31f7b`.
- **Unverified:** no whole-run A/B has played the new model. Its claim rests on the §543 offline replay, and the
  learned-stop default's claim rests on §538 with the old model and exact root budgets.
- The live advisor (`one_combat_advisor`) does not go through this resolution and keeps its own Silver budget.
