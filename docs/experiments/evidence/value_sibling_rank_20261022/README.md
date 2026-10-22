# Sibling-ranking loss and auxiliary heads for the OOC value head (2026-10-22)

Exploratory and offline. [PLAN.md](PLAN.md) is the plan as it was written before any run. It is a frozen copy of
`gen2/value-sr/PLAN.md` on the data branch `claude/az-gen2-data` at `5a0bb2e` (sha256 `1e565ce5…`).
- Philipp chose "more offline research before any play test" on 2026-10-22 at 09:51Z and asked about auxiliary
  targets at 10:02Z.
- Training ran on Philipp's GPU ("Merge 808 and go for gpu", 10:1xZ; seeds: "Merge 810, start gpu", 12:45Z).
- Evaluation ran in the cloud.

## Question
Can the value head learn to rank one decision's children the way their rollout3 targets do?
- Every head so far ranks round-2 VALIDATION siblings at about 0.55 concordance, against X2-B's 0.633 (§577, §622,
  §636).
- Fixing the head's slopes did not change that (§622).
- A 15 % logit blend with X2-B gained +0.011 (§636).

## Setup
- **Training data:** `r2_train_groups.jsonl.gz` (sha256 `b1933cc4…`), built by
  [tools/sr_groups.py](tools/sr_groups.py) from the §503 round-2 **TRAIN** delivery.
  - 8,458 groups from 1,088 sources, with at most 8 rows per action.
  - Each target is the mean of the 64 rollout3 values. A rollout3 value is X2-B after three CTM fights, or the
    terminal value.
  - Holdout: sources with seed % 8 == 6 (1,004 groups) are never trained on.
- **Recipe:** every arm is M0.3 (§622: student_sel init, VDF_T1 v0.5 targets, monotone hinge 0.3, seed 0, the same
  selection rule) with exactly one change:
  - SR_w*: `--sr-weight w`. Each step adds a batch of 16 groups (at most 2 rows per action). The loss is RankNet over
    the group's row pairs, weighted by the target gap.
  - AUX0.3: `--aux-weight 0.3`, which adds training-only heads for passing the next boss, reaching Act 4, and final
    floor / 55.
  - Code: `gen2/value-sr/tools/distill.py` (sha256 `1443c205…`) and `run_sr.sh` (modes `all` and `seeds`) on the data
    branch.
- **Control:** M0.3 seed 0 (`gen2/value-cf/weights/M0.3`, sha256 `ee8337a2…`). M0.3 seeds 1–2 show the seed spread
  (±0.002).
- **Evaluation:** [tools/eval_runs.sh](tools/eval_runs.sh) runs three steps.
  - `value_leaf_check.py check` scores the native export with `one_combat` `193b0000…`.
  - [tools/sr_eval.py](tools/sr_eval.py) computes §577 concordance (per-source mean, then over sources) with a paired
    source bootstrap.
    - The primary metric is round-2 **VALIDATION** (2,559 groups from 320 sources, never trained on).
    - The blend is sigmoid((1 − w)·logit X2-B + w·logit head), with w chosen on the TRAIN holdout.
  - The prices check runs on 38,819 perturbed records.
- **Gate (per arm):**
  - PASS: VALIDATION ≥ 0.633.
  - PARTIAL: ≥ 0.585.
  - Both also need the bars: selection-fold value BCE ≤ 0.552 and "−3 HP sign" ≥ 85 %.

## Results

| arm | sel BCE / AUC | training holdout | VALIDATION | − X2-B | − M0.3 | §494 | blend: w, VALIDATION, − X2-B | outcome AUC / BCE | −3 HP sign | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| X2-B | – | 0.642 | **0.633** | – | – | 0.601 | – | 0.683 / – | – | reference |
| M0.3 (control) | 0.5365 / 0.770 | 0.554 | 0.555 | −0.078 | – | 0.563 | 0.15, 0.644, +0.011 [+0.001, +0.021] | 0.700 / 0.429 | 89.4 % | – |
| AUX0.3 | 0.5398 / 0.767 | 0.550 | 0.557 | −0.076 | +0.002 [−0.003, +0.006] | 0.563 | 0.10, 0.648, +0.014 [+0.006, +0.023] | 0.697 / 0.427 | 88.8 % | FAIL |
| SR_w0.1 | 0.5362 / 0.771 | 0.588 | 0.586 | −0.048 [−0.063, −0.031] | +0.030 [+0.019, +0.041] | 0.588 | 0.10, 0.657, +0.024 [+0.016, +0.032] | 0.698 / 0.431 | 91.5 % | PARTIAL |
| SR_w0.3 | 0.5363 / 0.772 | 0.618 | 0.613 | −0.020 [−0.036, −0.002] | +0.058 [+0.044, +0.072] | 0.606 | 0.15, 0.666, +0.033 [+0.023, +0.044] | 0.693 / 0.442 | 92.0 % | PARTIAL |
| SR_w1 | 0.5466 / 0.763 | 0.649 | **0.644** | +0.011 [−0.004, +0.026] | +0.088 [+0.075, +0.102] | 0.634 | 0.05, **0.673**, +0.040 [+0.030, +0.049] | 0.672 / 0.501 | 88.1 % | **PASS** |

- "Training holdout" is the TRAIN holdout sources scored by the C++ export (`sr_eval.py`, 1,078 groups; Wing Boots
  groups included).
  - The in-training report (`distill.py`, 1,004 groups, Wing Boots groups dropped) gives X2-B 0.645. The arms there
    reach SR_w0.1 0.570, SR_w0.3 0.610, SR_w1 0.653 and AUX0.3 0.540.
  - Their per-epoch curves were still rising when the value metric stopped training. SR_w1 reached 0.668 at epoch 10
    against 0.653 at its selected epoch 7 ([results/train_summaries.json](results/train_summaries.json)).
- Outcome AUC/BCE use VALIDATION leaves against their source's Heart kill (base rate 0.18; a constant scores BCE 0.475,
  §577).
- Regret is in [results/](results/). For SR_w1 it is 0.0221 vs X2-B's 0.0232, and the SR_w1 blend's regret is −0.0024
  vs X2-B.
- Seeds 1–2 of SR_w1 are in the next section.

## Seeds of SR_w1 (the plan's step after a PASS)
SR_w1_s1 and SR_w1_s2 (`run_sr.sh seeds`, `--seed 1` and `--seed 2`) were trained on the GPU from 12:59Z.

| seed | selected / run epochs | sel BCE | training holdout (in-training) | VALIDATION | − X2-B | §494 | blend: w, VALIDATION, − X2-B | outcome AUC / BCE | −3 HP sign |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 7 / 10 | 0.5466 | 0.653 | 0.644 | +0.011 [−0.004, +0.026] | 0.634 | 0.05, 0.673, +0.040 [+0.030, +0.049] | 0.672 / 0.501 | 88.1 % |
| 1 | 6 / 9 | 0.5474 | 0.653 | 0.645 | +0.012 [−0.004, +0.029] | 0.632 | 0.25, 0.665, +0.032 [+0.019, +0.047] | 0.679 / 0.494 | 90.5 % |
| 2 | 4 / 7 | 0.5432 | 0.625 | 0.618 | −0.015 [−0.030, +0.001] | 0.608 | 0.10, 0.665, +0.032 [+0.023, +0.043] | 0.689 / 0.467 | 89.1 % |

- Two of three seeds are at or above X2-B's 0.633, and the mean is 0.636. Seed 2 is lower because the value objective
  stopped it at epoch 4. Its in-training holdout was still rising: 0.625 at the selected epoch, 0.645 at epoch 7.
  The spread therefore comes from the selection rule, which reads only the value metric, not from the ranking loss.
- The blend is stable: +0.032 to +0.040 over X2-B for all three seeds, every CI above 0. The holdout-chosen w varies
  (0.05–0.25) because the curve is flat.
- Monotonicity varies more than ranking between seeds. The selection-fold max-HP violation rate is 0.28, 0.35 and
  0.46, and gold+50 > 0 holds in 65 %, 81 % and 84 % ([results/prices_gate.txt](results/prices_gate.txt)).

## Noise-aware reading (exploratory, [tools/sr_noise.py](tools/sr_noise.py))
- **Label noise:**
  - Each target is a 64-rollout mean.
  - Rows of one action with the same X2-B value (the same public state) scatter 1.40× more than the rollout SE
    predicts. Hidden state differs between those captures.
  - With that inflation, a perfect evaluator would score about 0.81 on VALIDATION.
- **Noise-corrected concordance** (Σ(agree − p) / Σ(1 − 2p), where p = P(label order wrong)):

  | evaluator | X2-B | M0.3 | SR_w0.3 | SR_w1 | blend SR_w1 (w 0.15) |
  |---|---|---|---|---|---|
  | corrected | 0.710 | 0.602 | 0.671 | 0.720 | 0.764 |

  - On pairs whose target gap is at least 2 SE, X2-B and SR_w1 tie at 0.81.
  - The noise does not change the order of the evaluators.

## Where the gain is (exploratory, [tools/sr_breakdown.py](tools/sr_breakdown.py), VALIDATION)
- **By parent screen**, SR_w1 alone vs X2-B:
  - rewards +0.042 [+0.019, +0.066] (900 groups);
  - shop +0.041 [+0.019, +0.063] (365);
  - rest +0.007 (231);
  - map −0.013 (484);
  - event −0.035 [−0.062, −0.009] (502);
  - boss relic −0.147 [−0.223, −0.070] (59).
- **The SR_w1 blend (w 0.05)** is above X2-B on every screen except the boss relic (−0.021 [−0.039, −0.003]) and
  treasure (5 groups, tied).
  - By screen: event +0.039, rewards +0.044, map +0.037, shop +0.036, rest +0.020.
  - By act: Act 1 +0.055 [+0.043, +0.068], Acts 2–3 +0.019.
- **Blend weight** ([tools/blend_grid.py](tools/blend_grid.py), a finer grid after the fact):
  - The TRAIN holdout still picks w 0.05 for SR_w1. VALIDATION is flat at 0.669–0.675 for w 0.04–0.2.
  - SR_w0.3's holdout pick stays at 0.15.

## Reading
- **The ranking loss transfers to sources it never saw.**
  - VALIDATION concordance rises with the SR weight: 0.586, 0.613 and 0.644 for w 0.1, 0.3 and 1.
  - At weight 1 the head alone matches X2-B on X2-B's home metric: two of three seeds reach 0.644–0.645, and the mean
    is 0.636. The targets end in X2-B, which favours it.
  - Its blend beats X2-B by 0.032–0.040 for every seed.
- **Auxiliary heads do not help ranking.** AUX0.3 is within ±0.006 of M0.3. This is the second try, after VT_aux0.3.
- **The SR weight has a cost.**
  - SR_w1's selection BCE rises from 0.5365 to 0.5466, which is still under the 0.552 bar.
  - Its outcome BCE on VALIDATION leaves (0.501) is worse than a constant's (0.475).
  - Monotonicity weakens: gold+50 > 0 drops from 94 % to 65 %. Selection-fold violations rise to hp 0.21 and gold 0.18,
    against 0.13 and 0.08 at w 0.1.
  - A head used alone at rollout ends would therefore value levels worse. The blend uses the head only at 5–15 %.
- **Context:** online, gen 1b's head ranked siblings at only 0.547 but leaned +3.1 pp in Heart kills as the rollout3
  end value (§615, NOT_SHOWN). The offline sibling metric is a proxy for the online value.

## Files
- [PLAN.md](PLAN.md): the plan, frozen before any run.
- [tools/](tools/): `eval_runs.sh`, `sr_eval.py`, `sr_noise.py`, `sr_breakdown.py`, `blend_grid.py`, `sr_groups.py`, and
  `train_summaries.py`, which extracts the training numbers from the runs' `summary.json`.
- [results/](results/):
  - `sr_eval_<arm>.json`, plus `sr_eval_control_seeds.json` for M0.3 s0–s2 and CF_base;
  - the eval logs;
  - `prices_gate.txt`;
  - `train_summaries.json`;
  - `sr_noise_val.json` and `.txt`;
  - the breakdowns;
  - `blend_grid.txt`;
  - `weights.sha256`.
- **Weights and runs:** data branch `claude/az-gen2-data`, `gen2/value-sr/weights/<arm>/student.bin` and
  `gen2/value-sr/runs/<arm>/`. Commits:
  - SR_w0.3 `f5e53d6`
  - AUX0.3 `6a5b23d`
  - SR_w1 `3f0676b`
  - SR_w0.1 `8676e69`
  - SR_w1_s1 `6132469`
  - SR_w1_s2 `41d4a4d`
- **Input data, outside the repo:** the round-2 delivery (§503) and the §494 siblings, as for §636.
