# Combat Evaluator V1 — Stage B local evidence

This packet is for independent review. It contains three fresh, non-overlapping
128-source cohorts, their contract manifests, the combined 384-source corpus,
the fixed three-head XGBoost artifacts, and held-out predictions.

## Provenance

- Merged main SHA: `3b314c3d85f02315de7666d8c6542b568190c6e6`
- Producer executable SHA256: `e968d866d2fb3ccdb13d5d190e0f9802f2286aa0baa60ae80e7dbd6912e999c9`
- Teacher: `silver-ordinary-fair-c25-exact10k-1ef9aef`
- Seed blocks: `982216–982343`, `982344–982471`, `982472–982599`
- Combined CSV SHA256: `d05a9337785c36f538dc09627db519973a39cc565391add8bf7dbcb63812adb6`
- Combined manifest SHA256: `8aecfeb21323899674cb29c881fe7aa29eacf1ba1d84860d9bbc20ccf3c6e851`
- Feature count/order: `1017` / `5aaea1c942b4e6dc5c6212cbd56372cfaee43021574d5fadad28f9896165366`

Every shard and the combined corpus passed `tools/combat_evaluator_contract.py`
before training. Invalid escape rows were retained for auditability and excluded
from training and metrics.

## Corpus accounting

- Sources: 384
- Rows: 7,426
- Valid rows: 7,373
- Valid wins/deaths: 7,075 / 298
- Invalid rows: 53
- Quarantined sources: 32
- Quarantine reason: `escape` (all 53 invalid rows)
- Escaped rows counted as label-valid: 0

## Held-out result

The stable grouped split produced 5,262 train rows (5,223 valid), 1,045
validation rows (1,038 valid), and 1,119 test rows (1,112 valid). TEST contains
44 deaths, 38 nonambiguous deaths, 1,068 wins, and 6 ambiguous rows.

| Metric | Model | Train-prior / mean baseline |
|---|---:|---:|
| Survival logloss | 0.091747 | 0.166575 |
| Survival Brier | 0.023917 | 0.038003 |
| Survival AUC | 0.949587 | 0.500000 |
| Win-HP MAE / RMSE | 0.097385 / 0.137068 | 0.227909 / 0.271730 |
| Loss-remaining MAE / RMSE | 0.162139 / 0.190098 | 0.165817 / 0.201035 |
| Expected signed-score MAE / RMSE | 0.112671 / 0.171704 | 0.262913 / 0.331472 |

Sign confusion (actual rows, predicted columns): `[[23, 21], [10, 1058]]`.
Thresholded sign accuracy: `0.972122`.

Scientific verdict: **PROMISING**. Full act, roomClass, and sufficiently
populated encounter slices are recorded in `model.manifest.json`.

The trained model is an offline research artifact only. It has not been
integrated into runtime or OOC policy.
