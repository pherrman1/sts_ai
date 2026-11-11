# Gumbel distillation T0: result

[PREREG](PREREG.md) · D1 (1,024 runs, 569,059 roots) · code d156e42 · PC RTX 3060 Ti, 2026-11-10 evening · validation
split h = 1 (55,664 rows; boss rows 14,649), final checkpoints (`results/eval_summary.json`; value check
`results/t0_value.json`).

## Data (learning curves, q_regret in Silver score units)

| run | F = 0.125 | 0.25 | 0.5 | 1 | S2 (F = 1) |
|---|---|---|---|---|---|
| LC-P (visits, policy only) | 1.366 | 1.272 | 1.198 | 1.176 | 1.188 |
| LC-T (cq:20) | 1.393 | 1.276 | 1.191 | 1.159 (TG) | 1.163 |
| LC-N value NLL | 6.454 | 4.020 | 2.465 | 1.969 | 1.970 |

LC-P: Δ₁ 0.022 against Δ₂ / 2 = 0.037, so the policy is DATA_SATURATING. LC-T: Δ₁ 0.032 against 0.043, also
DATA_SATURATING. The value is still clearly data-limited in absolute terms. This motivated the 4,096-run factory
(D2).

## Target

q_regret at F = 1 on both seeds (D1 has no max backup, so this is mean Q):

| target | seed 1 | seed 2 |
|---|---|---|
| cq:20 | 1.159 | 1.163 |
| cq:5 | 1.184 | 1.186 |
| cq:paper | 1.194 | 1.197 |
| visits | 1.176 | 1.188 |

cq:20 is below visits on both seeds, by 0.017 / 0.025. That is more than the visits seed spread (0.012), so cq:20 is
BETTER_TARGET (learnability only, per the PREREG caveat). The policy CE to the visit shares rises from 1.525 to 1.987.

## Value (descriptive, h ≠ 0)

Root V (visit-weighted mean Q) lies below the fight's score:

| rows | bias | n | corr |
|---|---|---|---|
| all roots | −14.9 | 506,957 | 0.85 |
| boss | −20.9 | | |
| Act 4 | −26.4 | | |
| first root of each fight | −24.2 | | 0.55 |

The best-Q finalist has bias −12.5 (corr 0.87). It differs from the played pick on 2.7% of roots. The sharpness of the
targets (mean max probability) is 0.41 for visits, 0.59 for cq:5, 0.73 for cq:20 and 0.98 for cq:paper.

## Boss specialists (amendment 1, boss rows)

| run | q_regret, seed 1 / seed 2 |
|---|---|
| generalist | 1.499 |
| BOSS-P_e3 | 1.487 |
| BOSS-P_e11 | 1.475 / 1.481 |
| BOSS-FT_e3 | 1.477 / 1.461 |

The gains are only 0.02-0.04, about the size of the seed spread, so this is NO_SPECIALIST_GAIN. D1 is too small per
boss. D2 and T1 then gave 52-158k roots per boss.
