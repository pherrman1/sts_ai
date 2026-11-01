# Value-gate checks (rank 5 of the search-and-value literature review, #927) (2026-11-01)

Philipp, 2026-11-01 07:25Z: run item 5 of #927's cheap checks in its own thread. Three offline computations on
existing data; no gameplay, no seeds, no new captures. Decision rules are the ones stated in
[search-and-value-literature.md](../../../knowledge-base/research/search-and-value-literature.md) (table, rank 5)
before these numbers were computed:
- (a) subgroup gain visible but aggregate flat → replace the BCE gate by targeted probes;
- (b) extrapolated R² < 0.33 at 10^5 entries → no outcome-only capture (~23k core-h);
- (c) best head within ~0.05 of the simulated ceiling → stop outcome-label value work.

Result and interpretation: [RESULT.md](RESULT.md).

## Data
- (a), (b): #915's V_A4 data (`value_a4_improve_20261030`): `a4.pkl` (253e3178…), `run1_a4.pkl` (2911d98b…),
  `more_a4.pkl` (5432e85a…) from `/mnt/project-files/value-clean-labels/` and `/mnt/project-files/value-a4-improve/`
  (hashes checked). #915's protocol unchanged: dev pool seed % 4 != 3, 5-fold CV grouped by seed × 3 fold
  assignments, scored on dev core entries (2,174 entries, 3,798 games, 1,110 seeds); the TEST seeds stay unread.
  The ENS_all and ENS_rc out-of-fold scores reproduce #915's `exp6`/`exp8` logs to all printed digits
  (0.491048…, 0.490964…).
- (c): §644's common-seed VALIDATION (`ooc_sibling_crn_capture_20261022`): the 80 VALIDATION unit tars from
  `/mnt/project-files/ooc-sibling-crn/units/` (seed % 4 == 3), `crn_analyze.py rows` → 158,048 rows, 5,587 groups,
  1,364 at map roots (the README's counts). Head concordances from §715's
  [scale.json](../sr_ranking_vs_value_20261028/results/scale.json).

## Reproduce
Python 3.13, numpy 2.5.3, xgboost 3.0.5, scikit-learn 1.9.1, scipy 1.18.1; 4 cores, ~10 min each.
```
VA4_DATA=DIR python3 tools/va4_checks.py results/va4_checks.json            # (a) + (b)
# (c): extract the 80 VALIDATION tars into X (out/units/<seed>/...), then
python3 ../ooc_sibling_crn_capture_20261022/tools/crn_analyze.py rows X ROWS
python3 tools/sibling_ceiling.py X ROWS ../sr_ranking_vs_value_20261028/results/scale.json results/sibling_ceiling.json
```
Logs in [results/](results/) are those runs, raw. The ceiling script was run twice; the first run lacked the
variance-matched variants (`vm*`), which were added after seeing that the posterior-mean truth (`js`) is too smooth by
construction. Both runs share every other number; only the second is kept.
