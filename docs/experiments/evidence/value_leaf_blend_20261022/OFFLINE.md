# Value head: M0.3 seeds and an X2-B/value-head leaf blend (2026-10-22, exploratory)

## 1. M0.3 (monotonicity hinge 0.3 on the VDF_T1 v0.5 recipe) over seeds
Runs on data branch `claude/az-gen2-data` `c3bd827a`, `gen2/value-cf/` (same rows and folds; seed = training RNG only).

| run | sel KL | sel BCE / AUC | val BCE / AUC | prices: max HP +5 > 0 / HP monotone / −3 HP sign | R2 sibling conc | R2 outcome AUC |
|---|---|---|---|---|---|---|
| control s0 (CF_base) | 0.0591 | 0.5419 / 0.766 | 0.5118 / 0.774 | 19 % / 52 % / 81 % | 0.549 | 0.761 |
| control s1 | 0.0571 | 0.5422 / 0.762 | 0.5138 / 0.770 | 18 % / 55 % / 82 % | 0.549 | 0.758 |
| M0.3 s0 | 0.0596 | 0.5365 / 0.770 | 0.5074 / 0.780 | 67 % / 89 % / 89 % | 0.554 | 0.764 |
| M0.3 s1 | 0.0570 | 0.5395 / 0.765 | 0.5102 / 0.776 | 61 % / 89 % / 90 % | 0.552 | 0.759 |
| M0.3 s2 | 0.0583 | 0.5403 / 0.765 | 0.5122 / 0.775 | 51 % / 89 % / 89 % | 0.551 | 0.758 |

Reading: the hinge's value gain is small (val BCE 0.5099 vs 0.5128, seed means; M0.3's seed range is 0.005); its
monotonicity gain is large and consistent on all three seeds; sibling ranking and outcome AUC are unchanged (X2-B:
0.633 / 0.694).

## 2. Leaf blend v = sigmoid((1 − w) · logit(X2-B) + w · logit(head)) (exploratory, not pre-registered)
§577 data and aggregation (`tools/heart1/value_leaf_check.py`), w = 0 reproduces X2-B exactly (R2 0.633, §494 0.601).
w chosen on round-2 TRAIN sources by concordance; reported on round-2 VALIDATION (320 sources) and §494; source
bootstrap 2,000. Script [tools/blend2.py](tools/blend2.py), results `results/blend2-*.json`.

| head | w (train pick) | R2 val conc − X2-B | R2 val regret − X2-B | §494 conc − X2-B | outcome AUC val (X2-B 0.683) [CI of Δ] | outcome AUC all (X2-B 0.694) [CI of Δ] | mean leaf |
|---|---|---|---|---|---|---|---|
| M0.3 s0 | 0.15 | +0.011 [+0.001, +0.021] | −0.0005 [−0.0017, +0.0006] | +0.015 [−0.003, +0.036] | 0.699 [+0.002, +0.034] | 0.716 [+0.018, +0.027] | 0.725 |
| M0.3 s1 | 0.15 | +0.012 [+0.002, +0.021] | −0.0005 [−0.0016, +0.0007] | +0.014 [−0.002, +0.031] | 0.698 [+0.001, +0.032] | 0.715 [+0.017, +0.026] | 0.726 |
| control s0 | 0.15 | +0.010 [−0.000, +0.020] | −0.0006 [−0.0017, +0.0005] | +0.011 [−0.012, +0.035] | 0.699 [+0.002, +0.034] | 0.716 [+0.018, +0.027] | 0.725 |

Curve (M0.3 s0, R2 val concordance): w 0 0.633, 0.05 0.647, 0.1 0.649, 0.15 0.644, 0.2 0.644, 0.25 0.640, 0.33 0.629,
0.5 0.612, 0.67 0.593, 1 0.555. Outcome AUC (val) keeps rising over the scored w: 0.699 / 0.704 / 0.714 at 0.15 / 0.2 /
0.33, where concordance is already below X2-B. Per act (R2 val groups, w 0.15 / X2-B / head alone): act 1 (1,203)
0.669 / 0.663 / 0.537, act 2 (830) 0.637 / 0.625 / 0.584, act 3 (464) 0.608 / 0.587 / 0.574, act 4 (62) 0.545 / 0.536 /
0.543 ([stdout](results/blend2-M0.3.stdout.txt)).

Caveats: the sibling target is the mean of 64 rollout3 that END in X2-B (favours X2-B, so the blend's gain is against
that bias); online the leaf value is taken at the rollout3 end state, which this data cannot score; the learned OOC
stop was trained on the X2-B scale (blend mean 0.73 vs 0.79). Inference: the head carries run-level information X2-B
lacks, and a small blend keeps X2-B's act-1 sibling ranking, which the pure head loses offline (0.537). Online, the
pure gen-1b head as rollout3 end value (§615) showed no act-1 penalty, so this offline gap need not cost play.

## Provenance and reproduction
- Heads (native exports, data branch `claude/az-gen2-data` `c3bd827a`, `gen2/value-cf/weights/<run>/student.bin`):
  control s0 `42a6589f…`, control s1 `2c911ff4…`, M0.3 s0 `ee8337a2…`, s1 `a720de36…`, s2 `34e0789c…`. Recipe and
  code: [§622 evidence](../value_cf_distill_20261022/) (`--mono-weight 0.3`, `--seed 1|2`; control = no mono).
- Scoring: `one_combat` `193b0000…` (the §577 binary, from the share's bin-cache) `heart1score`, cwd repo root, no
  STS_* env. Data: §494 `corpus-train-validation.tar` (`03d29264…`, TEST not read) and the §503 round-2 TRAIN +
  VALIDATION deliveries (`*.sib.jsonl`, `*.states.jsonl`; CONFIRM not opened), extracted as in §577's OFFLINE.md.
- Sibling/outcome numbers: `python3 tools/heart1/value_leaf_check.py check <one_combat> out.json <work> <§494> <r2>
  NAME=<head.bin> ...` ([results/value_leaf_check_seeds.json](results/value_leaf_check_seeds.json) for the new seeds;
  seed-0 heads in [§622's](../value_cf_distill_20261022/results/value_leaf_check.json)). Blend:
  `python3 tools/blend2.py <work> <§494> <r2> <NAME>` reads that run's `<work>/{s494,r2}-<NAME>-out.jsonl`.
- Prices: `prices.py build/analyze` (`/mnt/project-files/silver-leaf-eval/ooc-label-leaf/prices.py`, 2,916 round-2
  REWARDS states) + [tools/prices_gate.py](tools/prices_gate.py); outputs in `results/`.
- No gameplay seeds; exploratory (w was not pre-registered; chosen on round-2 TRAIN before looking at VALIDATION per head).
- Code option for an online test: `STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT` (default off), smoke in [SMOKE.md](SMOKE.md).
