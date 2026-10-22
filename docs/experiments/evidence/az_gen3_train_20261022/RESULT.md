# AZ gen 3 prior training: result (offline)

Plan: `PLAN.md` here. Run on Philipp's GPU 2026-10-22 14:33Z-17:21Z. Results, logs, weights and parity on the data
branch `claude/az-gen2-data` @ `9866689b` under `gen3/` (`results.md`, `runs/*/summary.json`, `weights/SHA256SUMS`).
Copies here: `results_data_branch.md` (that `results.md`) and `tools/` (the driver `run_g3.sh`, `calibrate_g3.py`,
`summarize_g3.py` and `convert_vtargets.py`, the gen-2 converter extended to `E-SEED` files). `distill.py` is the gen-2
value-target file on the data branch (`gen3/tools/distill.py`, sha256 `8aac69b6…`).

- Calibration (training folds, exploration excluded): nstep_v a −1.534, b 0.581 (n 606,077); root_v a −1.612, b 0.597.
- **Pick (plan rule): `G3_nstep_noEv`**: n-step value target, exploration runs teach policy only. Selection policy KL
  0.0506 (seeds 1, 2: 0.0506, 0.0509), below both gen-2 references on the same folds (gen-2 n-step 0.0525, gen-2 pick
  0.0547) and student_sel (0.1052). Export sha256 `d5780dee…`; native parity on 400 records: max |dlogit| 1.1e-05,
  0 argmax mismatches.

| run | sel KL | sel value BCE (const 0.592) | val KL | val top-1 | val AUC |
|---|---|---|---|---|---|
| G3_z | 0.0521 | 0.497 | 0.0505 | 0.934 | 0.761 |
| G3_nstep | 0.0512 | 0.551 | 0.0498 | 0.935 | 0.683 |
| **G3_nstep_noEv** (s0 / s1 / s2) | 0.0506 / 0.0506 / 0.0509 | 0.554 | 0.0493 / 0.0496 / 0.0496 | 0.934 | 0.681 |
| ref gen-2 n-step (`a70736fd`) | 0.0525 | 0.567 | 0.0514 | 0.933 | 0.667 |
| ref gen-2 pick (`fc32d8f4`) | 0.0547 | 0.513 | 0.0530 | 0.933 | 0.738 |
| ref student_sel (`cf6bf7fb`) | 0.1052 | 0.687 | 0.1252 | 0.933 | 0.403 |

- Dropping exploration value rows helps a little (0.0506 vs 0.0512); the n-step target beats z for the prior again
  (0.0512 vs 0.0521) while z keeps the best value head (AUC 0.761), which search does not use.
- **Inference:** the gain over the gen-2 pick is 7% in selection KL, much smaller than gen 2's gain over student_sel
  (48%), which was NOT_SHOWN online (§621). Top-1 is flat at 0.933-0.935 for every trained net. Offline rank stays a
  filter, not evidence of strength; only a paired A20 A/B against student_sel can show it.

## Addendum: does a new prior change decisions? (Philipp 17:27Z: which offline values matter online)
Native forward (`one_combat heart1score`, cloud build) of student_sel (`cf6bf7fb`), gen-2 pick (`fc32d8f4`) and the
gen-3 pick (`d5780dee`) on every validation-fold (seed % 8 == 7) policy row; "right" = matches the argmax of π′.
Scripts and full per-source / per-screen tables in `flip/` (`build.py` collects the rows, `analyze.py` scores them).

| roots | n | net | top choice ≠ student_sel's | at those flips: new net matches π′ / student_sel matches π′ / neither |
|---|---|---|---|---|
| searched with student_sel (gen 0, gen-1b A, gen-2 A, exploration) | 8,424 | gen 2 | 3.55% | 123 / 156 / 20 |
| | | gen 3 | 3.24% | 120 / 132 / 21 |
| searched with the gen-2 prior (gen-2 B) | 1,995 | gen 2 | 3.51% | 45 / 15 / 10 |
| | | gen 3 | 3.16% | 40 / 16 / 7 |

- Top-1 vs π′ on the student_sel-searched roots: student_sel 0.940, gen 2 0.936, gen 3 0.938. The search overrides
  student_sel's top choice at 6.0% of them; gen 3 predicts 120 of those 509 overrides but moves 132 roots that
  student_sel had right.
- π′ sides with whichever prior guided the search that produced it (student_sel-searched: student_sel wins the flips;
  gen-2-searched: the trained nets win 3:1). So the flips are close calls the search itself does not settle, and π′
  cannot referee them.
- **Inference:** a trained prior changes the top choice at about 3% of decisions, and those are near-ties under the
  current search. That fits gen 1b and gen 2 being NOT_SHOWN (§589, §621) and predicts the same for gen 3 at the
  A/B's resolution (about ±2.7 pp). Selection KL falls mainly because the nets grow more confident in moves student_sel
  already picks, which does not change play. Moves change only where the search's verdict changes, which needs better
  evaluation (leaf values) or more search, not a prior closer to π′.
