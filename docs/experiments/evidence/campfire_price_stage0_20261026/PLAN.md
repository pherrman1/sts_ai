# Dynamic campfire price, stage 0: offline price at real rest sites (plan, frozen before results, 2026-10-26)

Philipp, 2026-10-26: no fixed rules for rest vs smith; campfire choices should be priced dynamically. Scope doc:
https://claude.ai/artifact/G2qqNKYNNE9DUrPGHCtBnF ("yes lets go" for stage 0, 2026-10-26 22:24Z).

## Question

Can a model-only price, Q(option) = E[survive to the act's end × calibrated X2-B at the next act start], tell the
options of a real A20 rest site apart (Rest, Recall, Smith → card k), does it move the right way with HP, and does it
disagree with today's student_sel choice often enough to be worth a causal test (stage 1, campfire forks)?

## Today

At the A20 default (map-only search, ADR-0061) student_sel decides rest sites from its logits (option, then the
upgrade target as a second step); nothing prices HP against an upgrade. §683's searched arm (flat tree, rollout3 +
X2-B) did not change the rest rate (41% vs 40%).

## Instrument

`STS_OOC_CAMPFIRE_PRICE=PATH` (research, default off, this PR): at each real rest site, before anything decides it,
a forked child builds the OOC MCTS model of the live configuration and, for every legal root action, runs
`STS_OOC_CAMPFIRE_PRICE_N` rollouts of two prices with streams shared by the actions (common random numbers):

- **actEnd (primary):** the rollout plays on (student_sel policy, CTM fights) to the first map state of the next act
  and takes sigma(a_act + b·logit X2-B) there with the A20 M0 calibration (ADR-0057); a death first is 0.
- **leaf (reported):** the search's own leaf (rollout3 + M0-calibrated X2-B), i.e. what §683's D arm used.

The run is unchanged: the smoke replay of §683 MAP seed 111374100 reproduces all 399 trace rows including the outcome.

## Data (no new seeds)

The first 128 seeds of §683 (`ooc_map_only_search_20261024/units.txt`, 111374100–111374227), MAP arm, replayed at
this commit with the §683 MAP configuration plus `STS_SILVER_ACT4_STRONG=0` (`replay_unit.sh`). Each replay must
reproduce its §683 MAP trace (`trace_check.py --prefix`; replays stop at the first act-4 state, since stage 0 prices
acts 1–3). A replay that diverges is excluded and reported. N = 32 (best Smith target chosen on even repeats,
valued on odd repeats).

## Gates (analyze.py, actEnd price, rest sites of acts 1–3 with a legal Rest)

- **(a) separable:** |Rest − best Smith| > 2 paired SE on at least 50% of sites with both options.
- **(b) HP direction:** Spearman(Rest − best Smith, HP/maxHP) ≤ −0.2 with the seed-bootstrap 95% CI below 0.
- **(c) disagreement:** the price's best class (Rest / Smith / Recall / other) differs from the played class on at
  least 10% of sites.

All three pass → propose stage 1 (campfire forks, seeds and workers need Philipp's go). Any fails → STOP, record.
Reported, not gated: the same for the leaf price; rest rates by HP band, played vs price-preferred (the expert
audit's 40–60% band: bot rests 75%, Baalorlord 13%).

Deviation from the scope doc: "elites ahead" is not computed; HP is the only gated direction.
