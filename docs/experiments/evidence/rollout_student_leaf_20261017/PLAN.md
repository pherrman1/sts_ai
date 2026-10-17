# Pre-registered A20 paired A/B: §494 student leaf vs rollout3 leaf

Status: **frozen plan, not authorized, not run.** Execution requires Philipp's
explicit go, an independent pre-launch review, and the run commit pinned below
at launch time (`RUN_COMMIT` = the reviewed head of this PR or its merge).

## Question

With Arm C's prior and search fixed, does replacing the rollout3 leaf value
with the §494 student change A20 strength, at equal simulations and at
roughly equal MCTS CPU?

## Arms (shared seeds, fair play)

Common environment: Arm C as in [REPORT.md](REPORT.md) with
`STS_STOP_AFTER_ACT=0` (full runs), `STS_OOC_HEART1` = `studentc.bin`
(`eff2f74f…`).

| Arm | Difference from control |
|---|---|
| C (control) | none; rollout3 leaf, 512 sims |
| S (equal sims) | `STS_OOC_MCTS_LEAF_STUDENT=student494.bin` (`653db96e…`) |
| S3 (CPU-matched, optional) | as S with `STS_OOC_MCTS_SIMS=1536` (smoke: 3.4x cheaper per sim) |

Command per run: `bash tools/seed_guard.sh one_combat bestbench 10000 1 20 <seed> <csv>`,
`OMP_NUM_THREADS=1`.

## Seeds

128 fresh source seeds `111000200..111000327`, one run per seed per arm.

## Endpoints and decision rule

- **Primary:** act-3 clears (reached act 4), S vs C, paired by seed. Exact
  two-sided McNemar test on discordant pairs; 95% paired-difference CI by
  seed bootstrap (2,000 resamples, RNG 20261017).
  IMPROVED if S−C > 0 and p < 0.05; WORSE if S−C < 0 and p < 0.05;
  otherwise NOT_SHOWN. S3 vs C is judged the same way as a separate,
  pre-registered comparison (no multiplicity correction; both reported).
- **Secondary (descriptive):** Heart kills, final floor (paired mean), act-1
  deaths, MCTS CPU per OOC decision, wall time per run, student
  evaluations and fallbacks (fallback rate > 1% is reported as a defect).
- **Validity:** a run that crashes or misses its CSV is rerun once on the same
  seed; a pair with a second failure is excluded and reported. More than 4
  excluded pairs makes the result INVALID.

No default changes from this A/B alone; a positive result goes to Philipp for
the default decision.

## Budget

Control runs took about 100–670 s each on Arm C VAL receipts; the student arm
was about 2.2x faster in wall time in the smoke. Estimate: C ≈ 13 CPU-h,
S ≈ 6 CPU-h, S3 ≈ 13 CPU-h for 128 seeds each. Proposed execution: 32 hosted
worker threads, 4 seeds × arms each, one coordinator-launched wave.
