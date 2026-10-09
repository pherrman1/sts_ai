# A20 synthetic Silver corpus and transfer gate T1 (ledger §403)

## Provenance
- Generator: `one_combat silversynthgen` at `450376c8` (the §397 A0 corpus
  commit), Release build sha256 `8906180f6514d9d08ec8b9f458668ddf31de25e5279b1c321a092ffd5c774d05`
  (identical to the A0 corpus binary), [teacher.json](teacher.json) unchanged.
  Only change: ASC = 20 ([unit.sh](unit.sh)). No code change was needed:
  `silversynthgen` already takes ASC and plays runs to the end, and the
  simulator plays the A20 second Act-3 boss itself (`GameContext.cpp:1215`).
- Seeds: smoke `60009000..60009017` (natural) and `60009000..60009001`
  (perturbed); corpus natural `60000000..60001079`, perturbed
  `60002000..60003079`, 20 cloud workers x 4 cores.
- Features: `one_combat silversynthfeatures` at main `9268a04b`
  ([feat.sh](feat.sh)), for both the A20 corpus and the §397 A0 1x corpus.
- Gate: [PREREG-T1.md](PREREG-T1.md), written at 01:10Z on 2026-10-09 before any
  corpus row existed (kept in the project folder, not committed at the time).
  Script [t1.py](t1.py) (LightGBM 4.7.0, prior v2 recipe from
  `tools/silver_prior_v2.py`); raw output [t1-report.json](t1-report.json).
- Models (not committed, 35-43 MB): A0 arm = §400 `prior-v2.txt` sha256
  `2fd877a0…`; final A20 arm `prior-a20.txt` `855226d9…`; final Mixed arm
  `prior-mixed.txt` `e192c901…` (project folder `a20-synthetic-silver/t1-full-20261009/`).
- Correction after review: the first T1 run
  ([t1-report-incomplete-a0.json](t1-report-incomplete-a0.json), models
  `2bcd6a6b…` / `4689d172…`) was missing the features of two A0 natural units
  (56000099-9, 56000108-9; only their summary files survived a restart of the
  feature job). T1 was rerun on the complete A0 1x corpus (100,483 A0 train
  roots, as in §400); the tables below are from that rerun
  ([t1-report.json](t1-report.json)). The verdict is the same in both runs.

## Corpus
237 of 240 units ([corpus-units.json](corpus-units.json): per-unit row sha256
and counts): 2,133 runs, 18,553 fights, 310,766 roots, 853,626 leaves, 69,290
second teachers, 34,589 continuation roots, 0 invalid fights.

Deviation: three units were dropped because one seed each stalled for over
an hour inside the label searches (`FightRecorder::observe` ->
`SilverSearcher::step`). gdb on local reruns showed two of the three in
`rolloutToEnd` and one in `getOrCreateNode`; a worker reported ~1,750 hits of the turn-165 loop guard per
search on seed 60002492. Stall seeds: 60002492 (perturbed), 60002631
(perturbed), 60000997 (natural); dropped units perturbed-60002486-9,
perturbed-60002630-9, natural-60000990-9 (27 runs). Folds are by seed, so the
split is otherwise unchanged.

Corpus: 8.7 fights per run (A0 corpus 21.4). Smoke (18 natural runs): 9.8
fights per run, 72% of fights in Act 1, ~1 CPU-minute per natural run. Seed 60009006 beat both A20 Act-3 bosses.

## T1 result (A20 test fold, top-1 agreement with the 10k pick, %)

| slice | roots | seeds | A0 | A20 | Mixed | Mixed - A0 [95% CI] |
|---|---|---|---|---|---|---|
| all | 57,115 | 428 | 62.8 | 64.9 | 65.3 | +2.5 [+2.1, +2.8] |
| both 10k searches agree | 11,275 | 428 | 70.9 | 73.0 | 73.6 | +2.7 [+2.0, +3.4] |
| Act 1 | 42,586 | 428 | 65.9 | 68.5 | 68.8 | +3.0 [+2.6, +3.3] |
| Act 2 | 12,027 | 134 | 55.1 | 56.0 | 56.5 | +1.4 [+0.8, +2.1] |
| Act 3 | 2,502 | 17 | 48.5 | 45.9 | 47.9 | −0.6 [−2.6, +1.1] |
| boss fights | 8,252 | 231 | 55.7 | 57.1 | 57.6 | +1.9 [+1.1, +2.8] |
| Act-3 bosses (both) | 475 | 10 | 45.9 | 42.3 | 46.1 | +0.2 [−3.3, +4.0] |
| A20 second boss | 174 | 5 | 43.7 | 41.4 | 46.0 | +2.3 [−6.2, +10.7] |
| A0 test (descriptive) | 32,309 | 86 | 59.0 | 57.4 | 59.6 | +0.6 [+0.2, +1.0] |

A20 − A0 on all A20 test roots: +2.1 [+1.7, +2.5]. Training: A20 164k train
roots (val group xent 0.960, 4,931 iterations), Mixed 265k (0.953, stopped
at the 6,000-round cap); the A0 arm was trained on 100k A0 roots (§400).
The second-boss slice is the later of two Act-3 boss floors in a run; it has
only 5 test seeds and is descriptive. The independent review's own full
retrain gave Mixed − A0 = +2.4 [+2.1, +2.8] (LightGBM threading makes
retrains differ slightly).

Verdict per the pre-registered rule (≥ 3 pp with CI excluding 0): not passed.
T2 (replay at A20) was not run.

Caveat: accuracy levels are not comparable across ascensions. 75% of the A20
test roots are Act 1, where every arm scores higher, so 62.8% (A20 test) vs
59.0% (A0 test) does not by itself show transfer. The gate compares arms on
the same roots.
