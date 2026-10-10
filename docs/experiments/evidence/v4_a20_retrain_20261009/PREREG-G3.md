# G3: V4 Q head retrained on round 1 + round 2 A20 data (pre-registration)

Written before the G3 candidate was gated. Question as G2, with about twice the labels.

## Data

- Round 1 as in `PREREG-G2.md` (seeds 67M, 611 runs).
- Round 2 (Philipp 2026-10-10 09:41Z "50 workers x 4.5h"): same frozen commit `2c89ed97`,
  binary 4a3c9ecc and generator settings, brief
  `/mnt/project-files/v4-a20-retrain/BRIEF-worker-r2.md`, seeds 68000000+1000W+k,
  no new chunk after 13:45Z, hard stop 14:45Z. 48 of 50 workers ran (w48, w49 never
  launched); 168 chunk files (145 rc 0, 22 killed at the hard stop, 1 abort), 642 runs.
- Combined: 323 chunk files, 548,816 rows, 1,253 runs, 10,024 labeled decisions
  (7,889 with > 1 option).

## Training

- Split `split_r12.json`: round-1 split kept (488/123 seeds); round-2 seeds 80/20 with
  `random.Random(20261010)` -> 1,002 train / 251 validation seeds.
- Recipe identical to the G2 candidate: warm start from deployed V4 (import tool),
  `STRAT_Q_ONLY=1`, `STRAT_LABEL_SCALE=floor`, 30 epochs, patience 30, select best
  validation strict Q top-1. Reference on the 1,581 validation decisions: random 0.255,
  heuristic chosen action 0.341.

## Gate

- Stack as G1/G2, guard off, margin 1.0.
- Arms: C = current V4 (e62abd83), T = G3 candidate. Seeds **67300000..67300255** paired
  (256), A20.
- Primary: mean paired floor difference T - C, 95% paired bootstrap CI (10,000 reps,
  RNG 20261010). Secondary: wins, floor >= 50, rows differing.
- Decision: `RETRAIN_BETTER` if CI lower bound > 0; `RETRAIN_WORSE` if upper bound < 0;
  else `NOT_SHOWN`. No default change in any case.

## Candidate (fixed before the gate ran)

- `R2W30_best_qtop1.pt`: best validation strict Q top-1 **0.302** (epoch 1 of 30; deployed V4
  at init 0.268; heuristic chosen action 0.341). Exported as `v4_a20_r12.native`, sha256
  `08d239f9aeaff7cdd57afb2b45a9cbbd1495b1dc9ab51dc09f3c70a61d186b15` (32 parity checks
  pass; copy and log in `/mnt/project-files/v4-a20-retrain/models/`).
