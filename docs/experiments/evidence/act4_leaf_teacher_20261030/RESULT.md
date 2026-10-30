# Act-4 value models as a Silver combat leaf: teacher check (exploratory, 2026-10-30)

Philipp, 2026-10-29 22:10Z: "Maybe we can do an act4 combat test when we have the v4 leaf, we can use it as an combat
leaf as well". On 2026-10-30 (after §720, V_A4 PASS) he asked to go on, and at 12:32Z ("Ja") to fit a Heart-entry value.
Offline only: no seeds, no game runs, one 4-core container. Python 3.13, numpy 2.5.3, xgboost 3.0.5, scikit-learn 1.9.1.

## Why a teacher check first

A value model can only change Silver's play through the prices it puts on end states within one fight (HP, potions,
max HP), relative to the leaf formula (win: 53 + HP after the act heal + 11 per potion + 0.3 max HP for Fairy).
The design and gate are those of the 2026-10-21 note (`/mnt/project-files/silver-leaf-eval/ooc-label-leaf/DESIGN.md`):
score the model on real states as is and perturbed, convert ΔV to HP by the state's own 12-HP secant slope. The
leaf only uses relative prices, so if the model agrees with the formula there is nothing to probe.

Where it applies:
- the last act-3 boss when Act 4 follows: value after the fight = V_A4 at the Act-4 entry. The leaf already uses the
  HP after the 75% act heal (`postBattleHealedHp`), which is what V_A4 sees.
- Shield & Spear: value after the fight = V_H at the Heart entry (no rest site between them).

## 1. V_A4 (`teacher.py`, `results/va4_plain.json`, `results/va4_mono.json`)

`teacher.py` refits §720's G_5 and GC_5 with `fit_a4_run1.py`'s data, parameters and selection (VALIDATION BCE
0.5115 / 0.4766, identical to §720) and scores the 536 run-1 base entries. `teacher.py … mono` adds monotone
constraints (cur HP, max HP, HP fraction, each potion type, CTM logit).

| price at Act-4 entry (median) | G | GC | G monotone | formula |
|---|---|---|---|---|
| one held potion, HP | 9.2 | 9.2 | 8.2 | 11 |
| Fairy (held / added), HP | 21 / 18 | 18 / 9.5 | 19 / 15.5 | ≈ 37 |
| other potion types | flat 5-10 | flat 4-11 | | flat 11 |
| −3 HP lowers V (share of states) | 80% | 78% | 95% | 100% |
| max HP +5, HP fixed | −0.6 HP/pt | −0.4 | −0.67 | +0.3 (Fairy only) |

Monotone G: TEST BCE 0.532 vs 0.529 unconstrained (TEST read before in §720, not fresh).

## 2. V_H, Heart-entry value (`extract_heart.py`, `fit_heart.py`, `results/vh.json`)

States: the last act-4 MAP state on floor 55 (after Shield & Spear and its rewards) of every complete Act-4-strong
game that reached the Heart: run 1 (2,583, base + forks) and the stage-2 campaigns key-rules (733), expert-anchored
(829), gumbel-qcap (399), card-rule (288); 4,832 states, 66.7% Heart kills, extract sha256 `eb5d177b…`
(`/mnt/project-files/combat-gap-probe/va4-teacher/heart/heart.pkl`). Features as V_A4 (`s0.features`) + HP fraction
+ potion count; GC adds the logit of the Act-4 CTM's Heart survival. Monotone as above. Hyperparameters by 4-fold CV
grouped by seed on non-TEST seeds (seed % 4 ≠ 3). The TEST games' outcomes were read in stage 2 / §720, so the TEST
numbers below are descriptive, not a fresh gate.

| TEST (1,172 states, not fresh) | BCE | AUC |
|---|---|---|
| constant | 0.661 | — |
| logistic on HP, max HP, HP fraction, potion count | 0.544 | 0.771 |
| Act-4 CTM Heart row, recalibrated | 0.486 | 0.824 |
| G | 0.468 | 0.842 |
| GC | 0.464 | 0.842 |

GC − CTM_recal −0.022 [−0.040, −0.006]; G − CTM_recal −0.018 [−0.043, +0.007].

| price at Heart entry (median, all 4,832 states) | G | GC | formula |
|---|---|---|---|
| one held non-Fairy potion, HP | 13.1 | 12.6 | 11 |
| per type (n ≥ 15, 32 types) | 10-16 | 9-15 | flat 11 |
| Fairy, HP | 26.9 | 29.6 | ≈ 37 (max HP 88) |
| V per HP, pp: HP < 40% / 40-70% / ≥ 70% of max | 0.04 / 0.89 / 0.46 | 0.02 / 0.66 / 0.45 | linear |
| −1 HP lowers V / −3 HP | 45% / 79% | 37% / 68% | 100% |
| max HP +5, HP fixed | −0.07 HP/pt | −0.05 | 0 |

Only 7% of Heart entries are below 40% HP, so the flat low-HP slope is weakly identified. The −1 HP shares are low
because the GBM is piecewise constant (G: V never rises when HP drops, it often stays flat).

## Reading

- At both points the model's relative prices are close to the formula: a potion is worth 8-9 (Act-4 entry) and 12-13
  (Heart entry) HP against 11, and potion types are priced flat. Fairy is priced lower than the formula (15-30 vs ≈ 37).
- The models do not resolve 1-3 HP differences, which are what Silver's close decisions turn on, and price max HP
  with the wrong sign (they read HP as a fraction of max HP).
- A leaf built from them would move potion prices by 2-3 HP and the Fairy price by ≈ 10 HP. §716 measured potion
  weight 5 and 22 in fights: changes of that size move HP per fight by under 1.5 HP. The effect on Heart kills would be
  far below what a fight-level probe of affordable size can measure.

**Decision:** no Act-4 combat-leaf probe. End-state prices in Act 4 are not where the combat gap to Baalorlord is.
Teacher gate of the 2026-10-21 note: −3 HP sign ≥ 95% fails for all but monotone V_A4 G; Fairy ≥ 30 HP fails
(V_H GC 29.6 is the closest); max HP > 0 fails for all. Rerun these scripts on any later Act-4 value model.
