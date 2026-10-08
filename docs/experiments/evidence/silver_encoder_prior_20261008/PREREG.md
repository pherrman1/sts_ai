# Learned encoder Silver root prior: offline gates (pre-registration)

Written 2026-10-08 before any encoder was trained; committed before training.
Follows ledger §400. Philipp's go: 2026-10-08 15:18 UTC ("then tackle the
learned encoder thing").

- Data: the §397 corpus (corpus-450376c8), roots with >= 2 actions, tokenized
  from the wire by `tools/silver_encoder_prior.py build` (165,134 roots, every
  action resolved to its tokens). Folds by source seed as in §397/§400: train
  0-2, val 3 (early stopping and weight pick), test 4 (reported once).
- Model: transformer encoder over state tokens (cards by zone, monsters,
  potions, player statuses, relics, context), d 128, 3 layers, 4 heads, per-
  action logits from pointer-gathered tokens; per-root softmax cross-entropy
  vs the 10k visit shares; AdamW + one-cycle, 20 epochs, keep the best val
  cross-entropy epoch. One configuration is pre-registered; any other
  configuration tried is reported as exploratory.
- Gate 1 (fit, test fold 4): top-1 against the 10k pick on roots where the
  second 10k search agrees with the first. PASS if the encoder beats v2
  (§400 model, same roots) by >= 5 percentage points. Also reported: top-1 on
  all test roots, cross-entropy, v1.
- Gate 2 (replay, only if Gate 1 passes): the §400 test roots (4,094 natural
  roots with a second search, 2 replay seeds) via `silversynthreplay`, budgets
  256/1k/2k, prior = encoder softmax, bonus w*P/(1+n). Weight picked on the
  §400 validation roots at 1k from {200, 400, 800, 1600, 3200}. PASS if regret
  at 2k vs plain has a seed-clustered 95% CI upper bound < 0 AND the mean is
  below v2's 2k mean on the same runs.
- A Gate 2 pass only justifies proposing native inference and a fresh-seed
  online screen (Philipp's word). Nothing ships before the CTM full retrain.

## Stage 2: 5x corpus (added 2026-10-08 after Gate 1 failed, before any new data)

Gate 1 failed (encoder 63.4% vs v2 67.8% on agree test roots). An exploratory
learning curve (dropout 0.1, weight decay 0.05, 8 epochs) rose with data:
validation agree top-1 59.3 / 61.4 / 64.3% at 33k / 67k / 100k training roots.
Philipp chose "5x corpus" (decision card, 19:02 UTC).

- New data: the same frozen generator (450376c8, one_combat sha256 8906180f…,
  same teacher.json), 20 cloud workers, seeds natural 58000000-58001079 and
  perturbed 58002000-58003079 (2,160 runs). Folds: seed % 5 (identical to the
  §397 rule for both corpora).
- Training data: folds 0-2 of the old and new corpora; early stopping on fold
  3 of both. Test: fold 4 of the OLD corpus only (the §400 test roots, so the
  numbers stay comparable).
- Arms retrained on the enlarged data with their fixed recipes: encoder (the
  regularized configuration of the learning curve: d 128, 3 layers, dropout
  0.1, weight decay 0.05, at most 12 epochs, best val cross-entropy) and v2
  (§400 recipe). Both are reported; v2-6x is the comparison for the gates.
- Gate 1': encoder agree top-1 on the old test fold >= v2-6x + 5 points.
- Gate 2': as Gate 2, against v2-6x, only if Gate 1' passes.
