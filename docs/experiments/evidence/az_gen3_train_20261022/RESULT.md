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
Native forward (`one_combat heart1score`, cloud build) of student_sel (`cf6bf7fb`), the gen-2 pick (`fc32d8f4`) and the
gen-3 pick (`d5780dee`) on validation-fold (seed % 8 == 7) roots, matched to the raw captures for each candidate's root
q, its visits and the move the search played. Scripts and outputs in `flip/`:
- `build.py` + `analyze.py` cover the policy rows (full-budget roots; per source and per screen).
- `margins.py` reports root q at the roots where the nets disagree.
- `fastroots.py` covers the searched roots without a policy row (learned stop / 1024 cap).
- `agree.py` reports gen 3 vs gen 2 agreement.

"Departures" are the roots where a trained net's top choice differs from student_sel's.

| roots searched with student_sel (gen 0, gen-1b A, gen-2 A, exploration) | n | gen 3 ≠ student_sel | gen 2 ≠ student_sel | gen 3 ≠ gen 2 |
|---|---|---|---|---|
| full budget (policy rows) | 8,424 | 3.24% | 3.55% | 2.08% |
| fast (median 512 completed sims) | 25,150 | 3.48% | 3.61% | 2.15% |

- **Gen 3 mostly repeats gen 2.** Of gen 3's 273 full-budget departures from student_sel, gen 2 picks the same move at
  196 (72%); at fast roots, 611 of 875 (70%). Gen 2 was NOT_SHOWN online (§621, +0.6 pp [−2.2, +3.3]).
- **The departures are not near-ties.** Both moves are well searched: median visits 1,693 vs 1,781 at full budget, and
  510 vs 511 at fast roots. Root q separates them by a median of 0.015 (fast roots 0.020), against 0.011 between the two
  best visited moves at all roots. Root q favours gen 3's move at 62% of full-budget departures, by a mean of +0.014
  (+0.9 pp calibrated Heart-kill probability).
- **What the search already does at the departures.**
  - Under student_sel it already plays gen 3's move at 120 of the 273 full-budget departures (fast roots: 367 of 875).
    There its q prefers that move by +0.049.
  - It keeps student_sel's move at 126 (fast roots: 397). There its q prefers student_sel's move by 0.023 (calibrated
    −1.1 pp; fast roots −0.6 pp).
  - The remaining 27 (fast roots: 111) play a third move.
  - Root q is the search's own verdict and favours the move it visited more, so it cannot say which move is truly
    better.
- **π′ agreement cannot referee either.** π′ is the guiding prior times exp(β · min-max-normalised q), with β 2.37, so
  at a departure the guiding prior's log-ratio often outweighs the q bonus.
  - On roots searched with student_sel, π′ matches student_sel at 132 departures and gen 3 at 120 (gen 2: 156 vs 123).
  - On 1,995 roots searched with the gen-2 prior it reverses: gen 3 40 vs student_sel 16, and gen 2 45 vs 15.
  - Top-1 vs π′ on the student_sel-searched roots is flat: student_sel 0.940, gen 2 0.936, gen 3 0.938.
- **Inference:**
  - A trained prior changes about 3% of top choices. The search already plays about half of them. The other half are
    the only place a new prior could change play, and there the search's own q prefers student_sel's move. Any gain
    would therefore need the search's evaluation to be wrong at those roots: it is a question about the evaluation, not
    the prior.
  - Selection KL falls mainly because the nets grow more confident in moves student_sel already picks.
  - With gen 3 repeating most of gen 2's departures and gen 2 NOT_SHOWN, a gen-3 A/B would most likely be NOT_SHOWN
    again at its resolution (about ±2.7 pp).
- This replaces the first version of this addendum (head `be6e7d91`). It called the departures "near-ties", which the
  root-q margins above do not support (review of #814).
