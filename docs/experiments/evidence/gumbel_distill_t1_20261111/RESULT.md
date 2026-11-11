# Gumbel distillation T1: result

[PREREG](PREREG.md) · data: D2 + D2b (702 units, freeze `results/FREEZE-T1.txt`, sha256 3089cacf…) · code 2abe6aa ·
PC RTX 3060 Ti, 2026-11-11 10:20-12:56 CET · all numbers: validation split (h = 1), final checkpoint
(`results/eval_summary.json`, from the eval.json of each run; transfer ref ppo-xfer/t1-results 62d93426).

## Data

pack_states: 702 files, 134,858 fights, 3,328,345 rows (multi-edge 3,119,117; droppedNoFight 1,000; chosenByCopy
22,611). tensorize: 3,328,345 rows, qb.npy with 19,534,120 edges. Train 2,671,927 rows, validation 330,542 rows, and
the gate holdout (h = 0) was not read. D2 units natural_111952416_8 and natural_111953592_8 (exhausted worker
attempts) and D2c are not in T1.

## Phase 1: generalists (validation 330,542 rows)

q_regret is in Silver score units and lower is better. The first number uses the max-backed Q (qb), the second the
mean Q (q). `top1` is agreement with the played Gumbel pick.

| run | F = 0.25 | F = 0.5 | F = 1 | S2 (F = 1) | top1 (F = 1) | policy CE |
|---|---|---|---|---|---|---|
| P-V (visits) | 1.383 / 1.281 | 1.319 / 1.224 | **1.286** / 1.194 | 1.288 / 1.196 | 0.490 | 1.554 |
| P-CQb (cq:20, backed) | 1.400 / 1.233 | 1.324 / 1.159 | 1.297 / **1.132** | 1.293 / 1.130 | 0.505 | 2.055 |
| P-CQm (cq:20, mean) | – | – | 1.404 / **1.111** | – | 0.489 | 2.091 |
| N (value 0.25, visits) | 1.531 | 1.438 | 1.383 | 1.387 | 0.478 | 1.561 |

The seed spread at F = 1 is 0.0014 (P-V), 0.0037 (P-CQb) and 0.0042 (N, backed).

N's value NLL is 4.684 / 2.183 / 1.661 at F = 0.25 / 0.5 / 1 (S2 1.662), with death ECE 0.0037 (S2 0.0033). On D1,
T0's LC-N reached 1.969.

**Decisions (PREREG rules):**
- **Target:** P-CQb's backed q_regret is higher than P-V's on both seeds (+0.010 / +0.005), so it is not BETTER_TARGET,
  and the phase 2 generalist is P-V_f1. The ranking turns around under the mean Q: there P-CQm 1.111 < P-CQb 1.13 <
  P-V 1.19. The cq targets also agree more with the played pick (top1 0.505 against 0.490). So the measure picks the
  winner, and T1 cannot say which target plays better (the PREREG caveat).
- **Data:**
  - P-V: Δ₁ 0.033 against Δ₂ / 2 = 0.032, so DATA_LIMITED, only just.
  - P-CQb: Δ₁ 0.027 against 0.038, so DATA_SATURATING.
  - N (value NLL): Δ₁ 0.52 against 1.25, so DATA_SATURATING by the rule, with a large absolute gain from F = 0.5 to 1.
  - Overall MIXED, leaning saturating. D2c (2,560 more runs) would buy little offline.
- The value head costs policy quality in the shared trunk again: N's backed q_regret is 1.383, against P-V's 1.286
  (as in §771).

## Phase 2 and amendment 1: boss nets (backed q_regret on each boss's validation rows)

- **SPEC:** P-V_f1 fine-tuned on one boss's rows (3 epochs).
- **BOSS-ALL** (amendment 1, Philipp 12:44 CET "What about only fine-tune on boss fights?", added during phase 2 and
  not pre-registered): P-V_f1 fine-tuned on all boss rows (`--rooms 2`, 3 epochs), then scored per boss.
- Two seeds each (s1 / s2). Δ is the mean of the two seeds minus the generalist.

| boss | val rows | generalist | SPEC s1 / s2 | BOSS-ALL s1 / s2 | Δ SPEC | Δ BOSS-ALL |
|---|---|---|---|---|---|---|
| HEXAGHOST | 7,145 | 0.765 | 0.725 / 0.714 | 0.759 / 0.750 | −0.045 | −0.010 |
| SLIME_BOSS | 6,421 | 1.585 | 1.443 / 1.456 | 1.495 / 1.469 | −0.136 | −0.104 |
| THE_GUARDIAN | 7,913 | 1.299 | 1.172 / 1.217 | 1.258 / 1.235 | −0.104 | −0.052 |
| AUTOMATON | 5,542 | 1.852 | 1.915 / 1.879 | 1.875 / 1.863 | +0.045 | +0.016 |
| CHAMP | 7,337 | 1.468 | 1.372 / 1.369 | 1.441 / 1.433 | −0.097 | −0.031 |
| COLLECTOR | 5,513 | 2.117 | 2.085 / 2.091 | 1.990 / 1.995 | −0.029 | −0.125 |
| AWAKENED_ONE | 12,388 | 2.379 | 2.288 / 2.309 | 2.272 / 2.263 | −0.081 | −0.112 |
| DONU_AND_DECA | 10,109 | 1.578 | 1.525 / 1.534 | 1.501 / 1.487 | −0.049 | −0.084 |
| TIME_EATER | 10,081 | 1.741 | 1.673 / 1.691 | 1.690 / 1.689 | −0.059 | −0.051 |
| SHIELD_AND_SPEAR | 11,036 | 2.037 | 2.011 / 1.994 | 2.073 / 2.087 | −0.035 | +0.043 |
| THE_HEART | 16,435 | 1.903 | 1.908 / 1.905 | 1.883 / 1.869 | +0.003 | −0.027 |

BOSS-ALL on all 85,566 boss validation rows scores 1.707 / 1.698.

**Specialist rule (PREREG):** SPEC is below the generalist on both seeds by more than the generalist's S2 spread
(0.0014). That gives **SPECIALIST_BETTER for 9 of 11 bosses**. AUTOMATON and THE_HEART get NO_SPECIALIST_GAIN.

**Caveat:** the rule's threshold is too small for these sets. The specialist seed spread reaches 0.046 (THE_GUARDIAN),
and the boss validation sets have 5.5-16k rows. Gains under about 0.03 are not secured. That covers COLLECTOR SPEC,
SHIELD_AND_SPEAR SPEC, HEXAGHOST BOSS-ALL and THE_HEART BOSS-ALL. On T0's D1 data (5-10k roots per boss), the shared
boss net gained only 0.02-0.04, so D2's 52-158k roots per boss make the boss nets learnable.

**Pattern (descriptive):**
- Per-boss specialists win in Act 1 (HEXAGHOST, SLIME_BOSS, THE_GUARDIAN), for CHAMP and for SHIELD_AND_SPEAR.
- The shared boss net wins for COLLECTOR, AWAKENED_ONE, DONU_AND_DECA and THE_HEART.
- TIME_EATER is a tie between the two.
- Nothing beats the generalist on AUTOMATON.

## Not run

The PREREG's descriptive value check (`t0_value_check.py`, root V under both Q sources against the fight score) was
not run on D2. It is left for T2's preparation.

## Reading

Distilling G16 + max backup into the net works offline at D2's size, and the cheapest further gain is boss-specific
fine-tuning. More data mainly helps the value head. Whether either helps Silver play is T2's question (root prior or
leaf value, SPRT gate on fresh seeds). T2 also has to choose the policy target: visits wins under the max-backed Q,
cq under the mean Q.
