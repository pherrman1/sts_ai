# Collector-specific prior data: pre-registration (written 2026-10-14 09:12Z, revised 09:36Z after pre-launch review; before any 95M data)

Philipp 08:58Z tapped "Collector data". Baseline: offline fine-tune of gen 4 on the existing Collector roots
gives fold-4 CE -0.0030 [-0.0039, -0.0020] (`../RESULT.md`); half the seeds gave -0.0010.

## Data
`one_combat silverazfocusgen` at code 1518989b (branch claude/project-thread-byhf2a), binary ad90e698,
10k flat exact Silver, gen-4 MLP tree prior (3ebeab9d) K=8, weight 400, root bonus off (same teacher
as gen 4 except the prior generation). The Collector is forced as act-2 boss; other fights unrecorded at
2k with the same prior; the first Collector fight is recorded as 4 copies (1 unperturbed, 3 perturbed),
then the run ends. Seeds 95000000-95002559 (2,560 runs, 640 units of 4). Expected about 200-260k roots
(author smokes 74067000-035: 103 roots per seed; reviewer smokes 74069050-062: 7 of 13 reached the Collector,
78 roots per seed; about 20 core-hours). A stalled unit (> 900 s) is killed with a backtrace and not rerun.

## Training
Analysis code frozen (in `..`): ft.py 603e1c3b, merge.py 5e95ff28, subpack.py b7d02211, evalpair.py c5eb1436
(sha256 prefixes; ft.py adds the old/new test summaries and `--train-frac` for the scaling curve).
Old Collector roots = `subpack.py 38` on the gen-4 pack; the new pack is appended with `merge.py`.
Pack the new data with `silver_az_mlp.py pack --drop-no-fight` (tag c95), add it to the existing
Collector roots (gen-4 pack, encounter 38). Folds seed % 5 as the loop. Fine-tune from gen 4 with
`ft.py` defaults (lr 2e-4, wd 1e-2, dropout 0.35, batch 512, LR halving, patience 8), train folds
0-2 of old + new, early stop on fold 3 of old + new.
Descriptive extras: lr 1e-4 and 5e-4.

## Primary metric and decision rule
Fold-4 CE on the OLD Collector test roots (the same 9,711 roots as RESULT.md), fine-tuned minus gen 4,
paired per root, seed-cluster bootstrap 95% CI. Secondary: the same on new fold-4 roots.
- d <= -0.0062 (at least one gen 3 -> gen 4 step on this fight) with CI below 0: CANDIDATE. Propose an
  online Collector-only paired check (gen 4 vs fight-specific prior), which needs Philipp's go.
- otherwise: NOT_WORTH_IT. Record and stop the fight-specific line.
Data-scaling curve (`--train-frac` 0.25/0.5/1 of new train seeds) is reported descriptively.
Note: earlier fights run at 2k sims, so HP/deck at the Collector differ somewhat from the old 10k roots the gate
is measured on; keep that in mind when reading the new-root metrics.
