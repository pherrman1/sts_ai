# Dynamic campfire price, stage 0b: the same sites at N = 128 (plan, frozen before results, 2026-10-27)

Philipp, 2026-10-27 12:06Z: "Merge 879 and try higher N price stage". Stage 0 (§695) stopped on precision: at
N = 32 the actEnd price separated Rest from the best Smith on 29% of rest sites (gate 50%), and only 12% of its
Rest/Smith disagreements with student_sel were separable. This stage asks whether 4x the rollouts fixes that.

## Question

At N = 128, does the actEnd price separate Rest from the best Smith at real A20 rest sites often enough, and are
its disagreements with the played choice real rather than sampling noise?

## Run (no new seeds, nothing new in the engine)

- Same instrument and binary as stage 0: `STS_OOC_CAMPFIRE_PRICE` from `38bd5a71`, binary sha256
  `46001555a23d53c8…`, student_sel `cf6bf7fb…`, run from a detached checkout of `38bd5a71` (so model files match).
- Same data: the first 128 §683 seeds (111374100–111374227), MAP arm, replayed with
  `../campfire_price_stage0_20261026/replay_unit.sh` (stage-0 configuration, `STOP_AT_ACT4=1`), but
  `STS_OOC_CAMPFIRE_PRICE_N=128`. 4 lanes in this thread's container.
- Each replay must reproduce its §683 MAP trace (`trace_check.py --prefix`); a diverging replay is excluded and
  reported. Forced-Ruby sites stay unpriced (§695).
- Analysis: `../campfire_price_stage0_20261026/analyze.py`, unchanged (best Smith picked on even repeats, valued
  on the 64 odd repeats; Rest valued on the same repeats).

## Gates (actEnd price, rest sites of acts 1–3 with a legal Rest)

- **(a) separable:** |Rest − best Smith| > 2 paired SE on at least 50% of sites with both options. (stage 0: 29%)
- **(b) HP direction:** Spearman(Rest − best Smith, HP/maxHP) ≤ −0.2 with the seed-bootstrap 95% CI below 0.
- **(c) disagreement:** the price's best class differs from the played class on at least 10% of sites.
- **(d) real disagreements (new):** among sites where the price prefers Rest and the bot smithed, or the reverse,
  at least 50% clear 2 SE (`c_swapsSeparable2se`). (stage 0: 12%)

All four pass → propose stage 1 (campfire forks; seeds and workers need Philipp's go). Any fails → STOP, record.

Reported, not gated: the leaf price; HP bands as in §695; how often the N = 32 and N = 128 prices pick the same
class at the same site (a direct read of stage 0's noise). Same seeds as stage 0, so this is a precision check on
the same sites, not a new sample of sites.

Expected cost: stage 0 took 21.8 lane-hours, of which pricing was about 0.9 h; N = 128 adds about 3 h of pricing,
so about 25 lane-hours, about 6–7 h wall on 4 lanes.
