# Act-4 survival model for the A20 CTM (§TBD)

- `PREREG.md`: the gate, written before the fit (commit `0bfa83b2`).
- `fit.json`: grid on VALIDATION and the selected cell; `gate.json`: TEST criteria and reported numbers.
- `natural_heart64.py` / `.txt`: descriptive check on the 64 natural Heart states of the F1 act4replay audit.

Reproduce (rows = the eight `/mnt/project-files/ctm-a20/act4-labels/w0*.tar.gz`, every `out/act4-*.jsonl` outside
`aborted-*`, concatenated in sorted path order, sha256 `c095368c…`):

```
one_combat ctmscorerows rows.jsonl base.csv selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native \
    selfplay/models/combat_transition_near_full_escape_pathb_a20.native 1
python3 tools/ctm_act4_survival.py fit rows.jsonl base.csv fit/      # model.ubj sha256 d9d1da66…
python3 tools/ctm_act4_survival.py gate rows.jsonl base.csv fit/
python3 tools/ctm_act4_survival.py export rows.jsonl fit/ models/candidates/ctm_act4_survival_trees.txt
python3 docs/experiments/evidence/ctm_act4_survival_20261018/natural_heart64.py \
    /mnt/project-files/audit-2026-10-17/f1-act4replay WORKDIR   # WORKDIR holds all.jsonl and fit/
```

XGBoost 3.4.1, NumPy 2.5.3, scikit-learn 1.9.1, 4 threads. The model file is
`models/candidates/ctm_act4_survival_trees.txt` (sha256 `05279b3c…`, 1,184 trees, 198 features).
