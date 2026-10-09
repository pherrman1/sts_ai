# Pre-registration: A20 transfer gate T1 (written 2026-10-09 ~01:10Z, before any corpus row exists)

Corpus: corpus-a20-450376c8/w00..w19 (silversynthgen at 450376c8, binary sha
8906180f…, ASC=20, natural 60000000-60001079, perturbed 60002000-60003079).
Features: `one_combat silversynthfeatures` at main 9268a04b (same feature code
as prior v2). Folds: (seed - base) % 5 with base 60000000 natural / 60002000
perturbed; train 0-2, val 3, test 4. Test fold is read once, at the end.

Arms (all v2 recipe: tools/silver_prior_v2.py PARAMS, listwise softmax,
early stopping on the arm's own val fold):
- (a) A0: existing prior-v2-20261008/prior-v2.txt (A0 1x corpus, unchanged).
- (b) A20: trained on A20 folds 0-2, val A20 fold 3.
- (c) Mixed: A0 1x corpus folds 0-2 + A20 folds 0-2, val A20 fold 3.

Metric: top-1 agreement with the recorded 10k pick (argmax visits) on A20
test-fold roots with >= 2 actions, natural + perturbed; secondary: roots where
the independent second 10k search agrees, and the group cross-entropy vs
visit shares. CI: 95% bootstrap clustered by source seed (2,000 resamples).

Decision:
- max((b),(c)) - (a) >= 3pp top-1 with CI excluding 0 -> A20 differs; run
  T2 replay at A20 (silversynthreplay, budgets 256/1k/2k, regret vs plain).
- Otherwise -> A0 knowledge transfers; no A20-specific prior route; A20 rows
  are offered as extra encoder data only.
Descriptive only (no decision): by act, boss fights, second-boss fights;
and (c) vs (a) on A0 test roots (does adding A20 data hurt A0).
