# #346 GBM transfer test: does A20 data help an A0 win model? (plan, written before training)

Authorized by Philipp on 2026-10-09 09:20 UTC: "Yes transfer/train the gbm, do
it in cloud if possible". Offline only; no games are played.

## Data (frozen)

- **A0:** E3 corpus (§396), `/mnt/project-files/ooc-cf-pilot/e3/`, map rows
  joined to `finalWon` by `tools/vwin_e3_cf.py` rules (invalid (state, k)
  groups dropped, E3's unfinished part skipped). Split by source seed with
  `source_split` (70/15/15). TEST stays closed.
- **A20:** §402 corpus, `/mnt/project-files/a20-transfer-346/cf-a20-5ba068e0/`,
  same rules. All A20 rows may be used for training (different seeds; no A0
  holdout leakage). For arm B's pretraining stop, A20 rows use the same
  `source_split` on their own seeds.
- **Features:** X2-B's public features (hidden-future fields dropped) plus
  `ascension` from the map rows (0 or 20; X2-B itself has no ascension input),
  the same feature list for every arm. Recipe: X2-B's XGBoost recipe as in E3,
  each state weighted 1, three xgboost seeds averaged.
- **Target:** `finalWon` at both ascensions. The A20 label is the A20 run win,
  about 10% positive (§402).

## Arms

At each rung, A0 training data is the first f of E3 TRAIN source seeds
(E3's `e3-curve-v1` order), with f in {10%, 25%, 50%, 100%}.

- **A (A0-only):** E3 TRAIN at fraction f.
- **C (mixed):** E3 TRAIN at fraction f plus all A20 rows, one model with
  `ascension` as an input.
- **B (A20 → A0):** a model pretrained on A20 rows (early stop on A20
  VALIDATION sources), then boosting continued on E3 TRAIN at fraction f.
- **E (A20-only, diagnostic):** the pretrained A20 model alone, scored on A0
  for ranking transfer. Its calibration is not expected to fit A0.

Early stopping for A, B and C uses E3 VALIDATION, as in E3. All arms share
that choice, so their comparison is fair, but absolute VALIDATION numbers are
slightly optimistic.

## Metrics and decision rule

- **Primary:** E3 VALIDATION map-row NLL on `finalWon`. For C − A and
  B − A at each rung: the mean per-row loss difference, with a 95% CI that
  resamples source seeds (2,000 draws).
- **Verdict, per arm (C and B separately):**
  - `TRANSFER_HELPS`: the NLL difference CI is entirely below 0 on at least
    2 of the 3 rungs at or below 50%, and the 100% rung's point
    difference is at most +0.002.
  - `TRANSFER_HURTS`: the CI is entirely above 0 on at least 2 of those 3
    rungs.
  - `INCONCLUSIVE`: anything else.
- **Secondary (descriptive):** Brier score, and boss-relic and card-reward
  selection gain vs V4 (E3's `selection_rows`) per arm and rung. Arm E's
  selection gain against arm A at 100% is the ranking-transfer readout.
- No promotion or default change follows from this test.

## Execution

`tools/vwin_a20_transfer.py`, run in one cloud container (4 threads). Output
goes to `/mnt/project-files/a20-transfer-346/transfer-<sha8>/`. The report
and a ledger entry follow.
