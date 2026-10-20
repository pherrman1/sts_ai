# ADR-TBD: Real combats under A20 OOC MCTS stop learned by default

Date: 2026-10-20
Status: accepted

## Context

With live OOC MCTS on, `runFullRunOOC` (`apps/one_combat/run_driver.cpp`) accepted only flat exact-10k Silver in real
combats. The guard came with the first live OOC MCTS, whose label and CTM teachers were exact 10k. The CTMs used now
were fit on learned-stop Silver: the `pathb-a20` Stage 1 teacher `silver-ordinary-fair-learnedstop-ctm-pathb-90f6df64`
(§443) and the §527 Act-4 labels. Without OOC MCTS, ADR-0051 already makes learned stopping the A20 default (§538:
non-inferior to flat 10k with g7f_E as root and tree prior, 0.49x run CPU).

PR #721 added `STS_OOC_MCTS_REAL_LEARNED_STOP=1` (default off). It requires learned stopping with exact root budgets on,
because exact root budgets off would multiply the boss budgets of imagined Silver fights. Imagined fights keep their
flat budget override and are unchanged. On 2026-10-20 at 05:31Z Philipp asked to "Merge 721 and turn the flag on".

## Decision

- Unset, `STS_OOC_MCTS_REAL_LEARNED_STOP` is on for ascension-20 runs with live OOC MCTS and off below.
- On, real combats need `STS_SILVER_LEARNED_STOP=1` and `STS_SILVER_EXACT_ROOT_BUDGETS=1` (adaptive, boss fallback and
  boss max off, reuse cap 32768, sims 10000); any other Silver setting is fatal and the error names the switch.
- `STS_OOC_MCTS_REAL_LEARNED_STOP=0` restores the flat exact-10k guard; `1` forces learned stopping below A20 too.

## Consequences

- A20 OOC MCTS configs that set `STS_SILVER_LEARNED_STOP=0` (every campaign up to gen 0) now fail at startup on main.
  Reproducing them needs `STS_OOC_MCTS_REAL_LEARNED_STOP=0`. Frozen campaigns on their own binaries are unaffected.
- `heartoutcomegen` at A20 needs `STS_SILVER_LEARNED_STOP=1` (ADR-0051 does not set it there) or the `=0` switch.
- With exact root budgets on, one-action real roots get a full search instead of being skipped.
- Real combat is about 2-3% of A20 OOC MCTS run CPU (`/mnt/project-files/a20-profile/REPORT.md`), so the CPU saving
  is small.
- **Unverified:** no A/B under OOC MCTS. The proposed check is paired A20 seeds on the gen-0 stack with
  `STS_OOC_MCTS_REAL_LEARNED_STOP=0` as control, primary Heart kills (non-inferiority).
