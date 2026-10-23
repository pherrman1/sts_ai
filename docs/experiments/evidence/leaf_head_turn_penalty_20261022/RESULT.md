# Result: leaf head with a per-turn penalty on exact first fights (2026-10-22)

**PASS.** The candidate selected on the tuning fights, hblend:a20:0.5/1 (50/50 blend of the silver-leaf-a20 head and
the playout, the head's value lowered by 1 point per turn beyond the root), meets every pre-registered bar on the 300
fresh fights (replays 111333000-099; 4,200 solves, no failures; `confirmation/`).

Exact regret per fight, paired against the playout (none):

| config | none | **hblend:a20:0.5/1** | hblend:a20:0.5 | head:a20 | head:ct | hblend:ct:0.5 | exact |
|---|---|---|---|---|---|---|---|
| prod | 0.790 | **−0.251 ± 0.054** | −0.324 ± 0.053 | +4.951 ± 1.327 | −0.302 ± 0.052 | −0.070 ± 0.045 | −0.268 ± 0.059 |
| prod@mb=4 | 0.456 | **−0.283 ± 0.048** | +0.118 ± 0.366 | +20.100 ± 5.294 | −0.251 ± 0.057 | −0.071 ± 0.035 | −0.355 ± 0.049 |

Selected mode by encounter (bar: none above +0.10): prod Cultist +0.012, Jaw Worm −0.690, Two Louse −0.076;
prod@mb=4 Cultist −0.108, Jaw Worm −0.705, Two Louse −0.038. Its gain is about that of a perfect leaf (exact) on
these fights. Without the penalty the blend stalled once with max backup (fight 111333070: 10 turns, regret 108, the
same 67 HP at the end as the playout's 2-turn win; with /1 it wins in 2 turns), and the head alone stalled as on the
first test (Two Louse +14.7 and +58.0; one fight 126 turns).

Played fights' own outcome (`outcome_tp.py`, end HP − 0.4 x turns, paired, no turn cap; descriptive):

| config | hblend:a20:0.5/1 | hblend:a20:0.5 | head:a20 | head:ct | exact |
|---|---|---|---|---|---|
| prod | +0.05 ± 0.16 | +0.11 ± 0.15 | −0.47 ± 0.23 | +0.08 ± 0.15 | +0.18 ± 0.14 |
| prod@mb=4 | +0.23 ± 0.14 | +0.25 ± 0.16 | −1.73 ± 0.55 | +0.29 ± 0.14 | +0.13 ± 0.16 |

All 300 fights are won in every mode. Even a perfect leaf moves the outcome of these easy fights by only about 0.2
points (Silver is 97-99% optimal on them); the regret, an expectation over the chance outcomes, is the sharper
measure of the decisions, and the outcome readout is consistent with it within its noise. The head alone loses
outcome only through stalls (Two Louse with max backup −4.3 ± 1.5).

Next (pre-registered): a native default-off leaf flag (the head, the blend weight and the turn penalty) and
fight-level A20 A/Bs on Philipp's go; Part B with the production-combat head a20prod after
`../silver_leaf_a20_prod_20261022`. Raw rows of tuning and confirmation:
`/mnt/project-files/exact-combat-research/leaf-value/turn-penalty/raw_tune_fresh.tgz`.
