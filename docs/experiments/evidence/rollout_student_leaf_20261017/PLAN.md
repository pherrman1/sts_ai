# Pre-registered A20 paired A/B: §494 student leaf vs rollout3 leaf

Status: **run complete 2026-10-17; result in [RESULT.md](RESULT.md) (ledger §504).** Philipp, 2026-10-17 08:20Z: "Merge, use 8
arms", then 08:20Z: "I mean 3 arms on 8 workers". Launch still requires the
independent pre-launch review. Code commit: `2709f712` (PR 584 merge); the run
commit is the reviewed commit carrying this file and the worker scripts.

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
| S3 (CPU-matched) | as S with `STS_OOC_MCTS_SIMS=1536` (smoke: 3.4x cheaper per sim) |

The exact per-arm environment is `arm_env.sh` (run under `env -i`; each unit
also writes its `STS_*` lines to `<unit>.env`). Command per unit, from
`run_unit.sh`: `timeout 4h bash tools/seed_guard.sh one_combat bestbench 10000 1 20 <seed> <csv>`.

## Seeds

128 fresh source seeds `111000400..111000527`, one run per seed per arm.

## Endpoints and decision rule

- **Primary:** act-3 clears (CSV `act` >= 4, i.e. reached Act 4), S vs C, paired by seed. Exact
  two-sided McNemar test on discordant pairs; 95% paired-difference CI by
  seed bootstrap (2,000 resamples, RNG 20261017).
  IMPROVED if S−C > 0 and p < 0.05; WORSE if S−C < 0 and p < 0.05;
  otherwise NOT_SHOWN. S3 vs C is judged the same way as a separate,
  pre-registered comparison (no multiplicity correction; both reported).
- **Secondary (descriptive):** Heart kills, final floor (paired mean), act-1
  deaths, MCTS CPU per OOC decision, wall time per run, student
  evaluations and fallbacks (fallback rate > 1% is reported as a defect).
- **Validity:** units are not rerun (a container restart reruns only an
  interrupted unit, whole). A unit counts when its `.done` line has rc=0 and its
  CSV has the seed's row; a seed without a counted unit in either arm of a
  comparison is excluded from that comparison and reported. More than 4 excluded
  seeds makes that comparison INVALID. Computed by
  `tools/analyze_rollout_student_ab.py analyze <out dirs>`.

No default changes from this A/B alone; a positive result goes to Philipp for
the default decision.

## Budget

Control runs took about 100–670 s each on Arm C VAL receipts; the student arm
was about 2.2x faster in wall time in the smoke. Estimate: C ≈ 13 CPU-h,
S ≈ 6 CPU-h, S3 ≈ 13 CPU-h for 128 seeds each. Execution: 8 hosted worker
threads (Philipp's count), each running 16 contiguous seeds × 3 arms = 48 units,
4 at a time (`worker.sh`); about 2–3 h per worker. Each worker uploads one tar
and one DONE file to the project share `rollout-student-494/ab/`.
