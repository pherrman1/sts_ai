# ADR-TBD: OOC MCTS defaults to the 1024:0.7 gap-ladder stop

Date: 2026-10-19
Status: accepted

## Context

OOC MCTS roots stopped early only at the exact visit lock, the point at which the runner-up could no longer catch
the leader. `STS_OOC_MCTS_GAP_STOP=1024:0.7` (§539) stops a root after 1,024 simulations when the top-two visit gap is
at least 70% of them, and keeps the visit leader.

- §539: offline, on 628 A20 roots, `1024:0.7` kept 99.2% of the full search's actions at an estimated 0.69x OOC CPU.
- §TBD-b (PR #680, `docs/experiments/evidence/ooc_stop_ab_20261018/`): 512 paired A20 seeds on the CTM-Act-4 stack
  (4096 sims, student_sel prior, temperature 1). The real combats used flat Silver 10k, before ADR-0051.
  - Gap ladder vs exact lock only: reached Act 4 +0.6 pp [−2.0, +3.1], NON_INFERIOR (margin −5 pp).
  - Heart kills 110 vs 106.
  - OOC MCTS CPU 0.69x, process CPU 0.80x.
  - The learned stop (TAU 0.99) was also NON_INFERIOR, at 0.53x OOC CPU. L − G on reaching Act 4 was −1.8 pp
    [−4.4, +0.9].

On 2026-10-19 at 21:58Z Philipp asked to "Make gap stop the default and merge".

## Decision

- `configureLiveOocMcts` (`apps/one_combat/ooc_mcts_adapter.cpp`) sets `STS_OOC_MCTS_GAP_STOP=1024:0.7` when the
  variable is unset, under these conditions:
  - root selection is by visits;
  - `STS_OOC_MCTS_SIMS` is above 1024;
  - `STS_OOC_MCTS_CPU_SECONDS` is not set;
  - `STS_OOC_MCTS_LEARNED_STOP` is unset or `0`. A learned stop therefore keeps the arm that was tested.
- `STS_OOC_MCTS_GAP_STOP=0` restores the exact visit lock only. An explicit ladder replaces the default and keeps its
  own checks.
- As before, the ladder is off on full-budget and observed-lock roots.
- The learned stop stays opt-in.
- `STS_OOC_MCTS_EARLY_STOP=0` does not turn the gap ladder off; a full-budget search needs
  `STS_OOC_MCTS_GAP_STOP=0` as well.

## Consequences

- OOC MCTS runs with more than 1024 simulations play differently and use less OOC CPU. Comparisons with earlier
  campaigns need `STS_OOC_MCTS_GAP_STOP=0`.
- Searches with 1024 or fewer simulations, Q selection or a CPU budget are unchanged.
- **Unverified:** the A/B covered A20 at 4096 sims and root temperature 1 only, so other ascensions, budgets and
  temperatures inherit the default without their own test. A lead of 70% of the votes depends little on the root
  temperature (Inference).
