# AZ gen 3 prior training: result (offline)

Plan: `PLAN.md` here. Run on Philipp's GPU 2026-10-22 14:33Z-17:21Z. Results, logs, weights and parity on the data
branch `claude/az-gen2-data` @ `9866689b` under `gen3/` (`results.md`, `runs/*/summary.json`, `weights/SHA256SUMS`).

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
