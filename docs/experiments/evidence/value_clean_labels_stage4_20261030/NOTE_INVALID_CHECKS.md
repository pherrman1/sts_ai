# Note (2026-10-31): checks (b)-(d) in stage5_full_result.json are invalid

`stage5_full.py` scored the real-state checks (b) real logloss, (c) HP inversions and (d) upgrade wrong-way on dense
arrays, while the XGBoost models were trained on CSR (absent = missing). Predictions on dense input are wrong
(validation logloss 0.48 sparse vs 1.10 dense). Concordance (a) used CSR and stands. See
`../value_clean_labels_capture2_20261030/RESULT.md` (fix 73e7b2f7 in stage5b.py) and the stage 4-5b ledger entry.
