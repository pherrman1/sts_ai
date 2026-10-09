# Step 0: outcome-label learning curve (2026-10-09)

Ledger: [§415](../../ledger-06.md). Pre-registration: [PREREG.md](PREREG.md) (committed at
`086fcf4b` before the run). Motivation and the proposed loop: [DESIGN.md](DESIGN.md).
Offline only: no gameplay seeds, #334 TEST components and E3 TEST states never opened.

## Run

- Tool `tools/vwin_outcome_curve.py` at `086fcf4b`, run on Philipp's machine in a
  `tools/agent/worktree.py` worktree at that commit; 264 s, 4 threads.
  Python 3.12.3, xgboost 3.4.0, pandas 3.0.5, numpy 2.5.1.
- #334 index `artifacts/vwin-refresh-334/a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json`
  (SHA-256 `ae56f963…0dfa00`); E3 root `build/e3-corpus/e3` (producer `8edf724c`; part w20/chunk1/part2
  unfinished and skipped, as in §396; 333 VALIDATION states).
- Anchor: `ALL` at 1/1 reproduces §394 P0 exactly (trees 278/355/373, NLL 0.42370).
- First attempt stopped at `mkdir` because the output directory had been pre-created; it was
  removed and the unchanged command rerun. stderr had only a pandas PerformanceWarning.
- Raw: [report.json](report.json) (SHA-256 `cfd045c4…2da98`), [run.log](run.log).

## Result

Pre-registered verdict on `SRC`: **INCONCLUSIVE** (neither GO nor STOP).

`SRC` (own-play source games, run-victory labels):

| games | trees (s0/1/2) | #334 VAL NLL | #334 gain pooled | E3 gain pooled | E3 boss relic | E3 card | E3 card skip |
|---|---|---|---|---|---|---|---|
| 87 | 1/3/1 | 0.534 | −0.011 | −0.038 | −0.075 | −0.000 | 0.236 |
| 174 | 1/2/2 | 0.550 | −0.008 | −0.048 | −0.097 | +0.000 | 0.243 |
| 348 | 37/31/27 | 0.496 | +0.004 | −0.030 | −0.079 | +0.017 | 0.225 |
| 696 | 48/43/58 | 0.469 | −0.006 | −0.037 | −0.072 | −0.002 | 0.221 |

Slope per doubling, pooled, source-clustered 95% CI: #334 VAL +0.0028 [−0.0010, +0.0066];
E3 VAL +0.0020 [−0.0038, +0.0077].

`ALL` (same sources plus counterfactual branch rows):

| sources | #334 VAL NLL | #334 gain pooled | E3 gain pooled | E3 boss relic | E3 card |
|---|---|---|---|---|---|
| 87 | 0.488 | −0.002 | −0.037 | −0.090 | +0.016 |
| 174 | 0.468 | −0.001 | −0.023 | −0.039 | −0.006 |
| 348 | 0.450 | +0.007 | −0.007 | −0.026 | +0.011 |
| 696 | 0.424 | +0.003 | −0.014 | −0.033 | +0.004 |

Slope: #334 VAL +0.0023 [−0.0026, +0.0070]; E3 VAL +0.0084 [−0.0003, +0.0172];
E3 boss relic +0.019 [+0.004, +0.033].

References (VALIDATION): uniform-random option E3 pooled −0.045 (boss relic −0.090);
oracle of K=2 +0.111.
