# Gumbel stop-trace data (2026-11-10)

Authorization: Philipp 2026-11-10 08:36 CET, "Go auf 40 worker", in the learned-stop thread. He approved the data step of
`docs/experiments/evidence/gumbel_stop_trace_20261110/SMOKE.md`. The gate (step 3) needs its own go.

## What runs

- **Units:** 1,024, one A20 whole run each, seed block 111430000-111431023. The smoke seeds are 111431100-111431109; 111431100 has been used.
- **Seed check:** no 111-prefixed seed or range in the repo's evidence, docs or tools touches 111420002-111439999. Model weight files are excluded from that scan.
- **What a run is:** the §775 G16 arm unchanged, as in `gumbel_wholerun_20261108/run_unit.sh`. That means Gumbel root k 16 at 16,000 simulations with max backup 4, and Act 4 strong's budgets in Act 4. net-0420 is the out-of-combat policy at temperature 0, without OOC MCTS. The only addition is `STS_SILVER_GUMBEL_STOP_TRACE`.
- **Binary:** code `ebd446b3` (the #1023 merge), release x86-64-v3, sha256 112c0f3a. This is the binary of the 18/18 identical replays.
- **Output:** each unit leaves `G16-SEED.{env,log,err,done}` and the trace `G16-SEED.csv.xz`.
- **Cost:** about 150 lane-h, about 1-2 h on 40 workers. The share needs about 0.1 GB (66 kB xz per short game, about 0.3 MB for a deep one) and about 1,100 files.

## Use

This is training data, not a test, so it has no decision rule. The plan:

1. Adapt `tools/silver_learned_stop.py` to these columns. Rows are grouped by root. The candidate stops are boundaries 0..P-1, and the label is `leader_is_final`.
2. Cross-validate by run.
3. Report agreement with the full-budget pick against the CPU fraction, as for ADR-0026 and ADR-0051.

The games also give a fresh descriptive G16 Heart rate. It is not a comparison: there is no control arm on these seeds.

Drops are games with rc != 0, a timeout, or no trace rows. They are listed, and their trace rows are left out of training.
