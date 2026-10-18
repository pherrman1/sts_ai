# ADR-0047: card-select students default to the target prior and rollout card selects

Date: 2026-10-17
Status: accepted

## Context

`student_sel.bin` (`cf6bf7fb…`, data branch `claude/heart1-distill-data` 5a7245aa, `results/E_d64_sel_xin/`) is
student C fine-tuned on heart1's CARD_SELECT labels. It also has the relic-counter, act and card-misc inputs
(`x_act`, `x_relic_counter`, `x_deck_misc`). Two options let it score card-select targets:
- `STS_OOC_MCTS_TARGET_PRIOR=1` scores compound smith/remove/transform targets in the tree;
- `STS_OOC_MCTS_LEAF_SELECTS=heart1` scores rollout card selects.

Both default off. ADR-0042 keeps them off for student C, whose select head is untrained.

§524 (64 paired A20 seeds) compared student_sel with both options on against student C. The result was NOT_SHOWN:
22 vs 18 runs reached Act 4 (p = 0.48) and Heart kills were 10 vs 7, at 1.11x wall time. In the §524 decision logs:
- With a Strike, Defend or curse available, student C removed another card 27 of 44 times; student_sel did so 2 of 65 times.
- Student C put 13 of 201 upgrades on a Strike or Defend; student_sel put 0 of 221.

These counts are descriptive. They were not pre-registered.

On 2026-10-17 Philipp decided, after seeing the result: "we definielty make this one standard", and "we should also
use this in the alpha zero loop".

## Decision

- `configureLiveOocMcts` turns the two options on by default when the loaded `STS_OOC_HEART1` weights carry the
  `x_act` input, as `student_sel.bin` does:
  - `STS_OOC_MCTS_TARGET_PRIOR=1` when the tree prior is heart1;
  - `STS_OOC_MCTS_LEAF_SELECTS=heart1` when the tree prior is heart1full and `STS_OOC_MCTS_LEAF_POLICY=heart1`.
- Setting either variable explicitly overrides the default. `STS_OOC_MCTS_TARGET_PRIOR=0` and
  `STS_OOC_MCTS_LEAF_SELECTS=chain` restore the old behaviour.
- Weights without `x_act`, such as student C `studentc.bin`, behave as before.
- `student_sel.bin` replaces student C as the standard A20 OOC weights in harnesses and AlphaZero-loop data
  collection.
- The tree's non-UPGRADE card-select screens stay uniform (`heart1FullScreen`, ADR-0042). This ADR does not change
  that exclusion.

## Consequences

- An A20 run is unchanged if it keeps `STS_OOC_HEART1=studentc.bin`. Switching to `student_sel.bin` also switches
  on both options.
- The live advisor's research stack (`LiveOocMctsPolicy`) applies the same rule, with the same two variables as
  overrides, and `tools/live_game_runtime.py` makes `student_sel.bin` its standard Arm C weights (student C is still
  accepted). An installed advisor changes only when it is reinstalled with `student_sel.bin`. (Correction
  2026-10-18: the first version of this ADR said the advisor already followed the rule; it did not.)
- **Unverified:** a playing-strength gain (§524 NOT_SHOWN).
- **Inference:** keying on `x_act` assumes that only select-distilled students carry that input. The select
  fine-tune is currently the only exporter of that input.

## Evidence

§524 and PR #631; `docs/experiments/evidence/student_sel_ab_20261017/`; `oocmctsselftest` parsing checks.
