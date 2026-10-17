# Student-leaf A20 A/B: result (2026-10-17)

**S (student leaf, 512 sims) WORSE; S3 (student leaf, 1536 sims) NOT_SHOWN.** Pre-registered in [PLAN.md](PLAN.md);
run commit `2efd7f35`, code `2709f712`, binary `4004a823…` on all 8 workers; 384/384 units rc 0, no exclusions,
no `[bestbench-seed-failure]`. A20 seeds 111000400–527, paired by seed. Analysis:
`tools/analyze_rollout_student_ab.py analyze <8 out dirs>` → [report.json](report.json); worker tars and sha256 in
[worker_tars.txt](worker_tars.txt) (project share `rollout-student-494/ab/`).

The endpoint is **reached Act 4** (CSV `act` ≥ 4). With keys collected, a run that clears the Act-3 boss without all
three keys would end `act` 3 with HP > 0; no run in any arm did (0/0/0).

| Arm | Reached Act 4 | Heart kills | Mean floor | Deaths act 1/2/3/4 | MCTS CPU s/decision | Wall s/run |
|---|---:|---:|---:|---|---:|---:|
| C rollout3, 512 | 45 | 20 | 39.9 | 18 / 43 / 22 / 25 | 4.44 | 453 |
| S student, 512 | 31 | 12 | 35.4 | 34 / 38 / 25 / 19 | 1.11 | 142 |
| S3 student, 1536 | 32 | 12 | 36.1 | 30 / 41 / 25 / 20 | 3.25 | 313 |

| Comparison | Δ reached Act 4 | 95% CI (seed bootstrap) | Discordant T/C | McNemar p | Label | Δ floor |
|---|---:|---|---|---:|---|---:|
| S − C | −10.9 pp | [−20.3, −1.6] | 11 / 25 | 0.029 | WORSE | −4.48 |
| S3 − C | −10.2 pp | [−19.5, 0.0] | 14 / 27 | 0.060 | NOT_SHOWN | −3.80 |

Student leaves: 2,251,885 (S) and 6,775,220 (S3) evaluations, 0 fallbacks. S3 spent 0.73x the control's MCTS CPU
per decision, not about 1x as planned: the one-seed smoke's 3.4x ratio did not hold over full runs (S was 4.0x
cheaper per decision than C).

**Inference (not tested):** the loss is concentrated in act 1 (act-1 deaths 18 → 34 / 30). §494's offline gain was
small (TEST concordance 0.656 vs X2-B 0.630, regret CI including zero), and the student's within-sibling ranking
apparently does not replace rollout3's combat-outcome signal in early decisions. Tripling simulations did not
recover the gap, so cheaper leaves buy no strength here. No default change; `STS_OOC_MCTS_LEAF_STUDENT` stays
research-only.

Budget note (review item): the PLAN's "100–670 s per control run" source could not be traced; observed control wall
time was 453 s per run on average.
