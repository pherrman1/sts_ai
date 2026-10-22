# Counterfactual teacher-delta distillation of the OOC value head: FAIL (2026-10-22)

Pre-registered plan: [PLAN.md](PLAN.md). All runs: VDF_T1 v0.5 recipe (d64/L2 from student_sel, lr 1e-4, anchor 0.3,
value weight 0.5, value target = T1 teacher value, no K), seed 0, `STS_ACTIVE_POWER_FEATURES` not involved (OOC net).
Code: gen-2 sweep `distill.py` (data branch `claude/az-gen2-data` `gen2/value-targets/tools/distill.py`) +
[tools/distill.py.patch](tools/distill.py.patch) (patched distill.py sha256 844541f6…), `monotone.py` from main (#777). Runs, weights and
native exports: data branch `02f2c60d`, `gen2/value-cf/`. GPU: Philipp's PC; offline checks in the cloud with
`one_combat` `193b0000…` (the §577 binary).

## Training metrics (selection fold, chosen epoch)
| run | KL | value BCE | AUC | CF sign agree hp/mhp/gold | mono viol hp/mhp/gold | epochs (sel/run) | wall |
|---|---|---|---|---|---|---|---|
| CF_base (control) | 0.0591 | 0.5419 | 0.766 | 67 / 30 / 72 % | 27 / 76 / 20 % | 10/13 | 33 min |
| CF_w0.3 | 0.0602 | 0.5708 | 0.730 | 85 / 88 / 87 % | 13 / 10 / 7 % | 17/20 | 74 min |
| CF_w1 | 0.0604 | 0.5961 | 0.709 | 86 / 90 / 87 % | 14 / 10 / 7 % | 18/20 | 75 min |
| CF_w3 | 0.0640 | 0.6175 | 0.682 | 86 / 91 / 88 % | 14 / 11 / 7 % | 19/20 | 74 min |
| M0.3 (hinge, comparison) | 0.0596 | 0.5365 | 0.770 | 75 / 70 / 82 % | 15 / 27 / 6 % | 11/14 | 36 min |

CF_base reproduces VDF_T1 v0.5 (sel BCE 0.542; its prices and sibling numbers are within 0.002 of the exported
5f14d3f6). Raw heart1 itself is wrong-signed on the same probes in 19 / 14 / 14 % of selection states. Before the CF
loss the student's deltas were 4-6x heart1's (mean −3 HP: −0.036 vs −0.010 logit); with it they match on average.

## prices.py (2,916 round-2 REWARDS states, §609 definitions)
| head | max HP +5 > 0 | −3 HP sign right | gold +50 > 0 | 12-HP slope p50 | non-Fairy potion HP-eq p50 | Fairy p50 | monotone 0/6/12/24 |
|---|---|---|---|---|---|---|---|
| VDF_T1 v0.5 / CF_base | 19 % | 81 % | 82 % | 0.00116 | 7.5 | 30.0 | 52 % |
| CF_w0.3 | 92 % | 90 % | 97 % | 0.00058 | 39.9 | 65.2 | 90 % |
| CF_w1 | 95 % | 89 % | 97 % | 0.00057 | 22.5 | 38.5 | 88 % |
| CF_w3 | 96 % | 89 % | 97 % | 0.00055 | 8.4 | 17.6 | 87 % |
| M0.3 | 67 % | 89 % | 94 % | 0.00122 | 11.2 | 34.4 | 89 % |
(max HP / gold rows over states with a positive 12-HP slope.)

## Sibling ranking and outcome (§577 tool, value_leaf_check.json; X2-B 0.633, one rollout3 0.590)
| head | R2 concordance | − X2-B [95% CI] | §494 concordance | R2 outcome AUC / BCE |
|---|---|---|---|---|
| VDF_T1 v0.5 | 0.549 | −0.084 [−0.092, −0.077] | 0.554 | 0.761 / 0.426 |
| CF_w0.3 | 0.558 | −0.075 [−0.084, −0.067] | 0.551 | 0.745 / 0.432 |
| CF_w1 | 0.548 | −0.085 [−0.093, −0.077] | 0.534 | 0.715 / 0.455 |
| CF_w3 | 0.555 | −0.078 [−0.086, −0.070] | 0.547 | 0.674 / 0.471 |
| M0.3 | 0.553 | −0.079 [−0.087, −0.071] | 0.563 | 0.764 / 0.426 |

## Verdict
**FAIL** (pre-registered gate): every CF weight fixes the slopes (sign agreement ≥ 85 %, max-HP price > 0 in ≥ 92 %)
but costs 0.029-0.076 selection BCE (bar: ≤ 0.545) and also misses KL ≤ 0.0600 (0.0602 / 0.0604 / 0.0640). The
−3 HP ≥ 95 % bar is also missed. Raw heart1 itself is wrong-signed on −3 HP in 19 % of selection-fold states (a
different population from the 2,916 REWARDS states), so a heart1-delta teacher is unlikely to reach it.

Inference:
- At d64/L2 with the sinusoid-only scalar encoding, matching heart1's small HP/gold deltas competes with fitting the
  value (the base student used HP/gold features with 4-6x heart1's slope as correlates of run strength).
- Correct slopes do not close the sibling gap: +0.009 at best (CF_w0.3), against −0.075 to X2-B. So the wrong
  end-state slopes are not what makes the head rank siblings poorly.
- The hinge on the T1 recipe (M0.3) behaved unlike §609 (z recipe): BCE 0.5365 (−0.005 vs control, one seed), HP
  monotone 89 % vs 52 %, max-HP price positive in 67 % vs 19 %, sibling +0.004. Best value head so far on every
  offline metric, but one seed and still far from X2-B on siblings.
- CF halves the HP slope (heart1's own slope is small), which inflates HP-equivalent prices (potion 40 HP at w0.3).

Omissions: seeds 1-2 not run; no native-vs-torch parity file for the new exports (export only); no online test.
