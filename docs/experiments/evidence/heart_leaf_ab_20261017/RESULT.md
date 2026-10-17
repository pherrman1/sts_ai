# §522 result: Heart leaf td2 vs X2-B leaf, A20 paired A/B

Plan and decision rule: [PLAN.md](PLAN.md). RUN_COMMIT `82d85b0e`, code `209c5613`, binary `20d03790…`,
8 workers × 64 seeds (111191000–111191511) × 2 arms, all 1,024 units rc 0, every H env with the td2 manifest and
no C env with it (checked per tar before release). No seed excluded. W6 lost one unit (H 111191381) to a container
restart; the worker reran it whole and moved the interrupted copy to `out/aborted-*`, which has no `.done` file and
is not read. Analyzer: `tools/analyze_heart_leaf_ab.py analyze COHORTS <8 out dirs>` → [report.json](report.json).

| 512 pairs | H (td2 leaf) | C (X2-B leaf) | H − C |
|---|---:|---:|---|
| **Reached Act 4 (primary)** | 124 | 137 | −2.5 pp [−6.4, +1.4], McNemar p = 0.24 (46 vs 59 discordant), **NOT_SHOWN** |
| Heart kills | 42 | 46 | −0.8 pp [−3.5, +2.1], p = 0.68 |
| Act-1 deaths | 114 | 69 | discordant 61 vs 16, exact McNemar p < 0.0001 (descriptive) |
| Act-3 deaths | 93 | 118 | discordant 49 vs 74, p = 0.03 (post hoc) |
| Mean final floor | | | −3.1 |
| MCTS CPU s per OOC decision | 2.68 | 2.68 | |
| Seconds per run | 252 | 275 | |

Most extra H act-1 deaths are at the act-1 boss (64 vs 40 deaths on floor 16).
**Inference:** td2 under-predicts Act-1 Heart chances (§515 CONFIRM 0.093 vs 0.130), which flattens leaf value
differences in Act 1; the extra deaths fit that, but this run does not test the mechanism.

Act-4 campfire (last campfire of a run reaching Act 4): C Rest 76, Smith 48, Dig 8, Lift 3, Leave 2; H Rest 77,
Smith 40, Lift 4, Leave 3, Dig 0. Event choices nearly match between arms (per-event counts in `report.json`).

**Hidden-queue footnote.** td2 was fitted on real-game roots that carried the hidden encounter queue
(`nextEliteId`, `nextFight0..2`), while play feeds it sampled queues. Shuffling those columns on §515 VALIDATION left
td2 unchanged, so the comparison stands as run; schema v4 (`heart_leaf_td3`, #642) removes them.

Raw: `/mnt/project-files/heart-leaf-td/ab/w0{1..8}.tar.gz` with `w0n.DONE.txt` (sha256 inside).
