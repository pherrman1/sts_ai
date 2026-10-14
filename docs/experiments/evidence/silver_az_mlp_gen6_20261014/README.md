# Silver AZ MLP prior, generation 6 (40k teacher; self-play data and offline training)

Ledger §478. Generation 6 with a 40k teacher (Philipp, 2026-10-14 11:14Z). Full numbers and the
decision: `RESULT.md` (copied from the share).

- Frozen: `FROZEN.md`, `BRIEF-worker.md` (sha 2d93088b), `worker.sh` (gdb backtrace + kill after
  7,200 s), `env.sh`; main `f73e6ad7`, binary `b4586cfc…`, prior gen 5 (`5e9f975a…`).
- Seeds: natural 97000000-97000511, perturbed 97001000-97001511, 8 workers. 256/256 units rc 0,
  no stalls.
- Training (`PLAN-train.md`; arm D added before any gen-6 data): A/B/C warm start from gen 5 with
  `tools/silver_az_mlp.py` on CPU (`train-runA/B/C.json`); teacher `g6_t512`, D, E and Eenc from
  scratch with the net-arch script on Philipp's GPU (`arch_dev.py` = the net-arch `arch.py`, share sha 3e736bba, plus
  `--device`; `train-g6_*.json`). `convert.py` turns D's
  checkpoint into the `tools/silver_az_mlp.py` export format.
- Gate table: `gate.json` from `gate_eval.py` (every arm with its own stored input scales, same
  pack and splits); D's values equal its training-run values, which checks the conversion.
- Parity: D `g6Dparity_*.json` (pass); E and Eenc exported as `combat_policy_mlp_v2` in
  `../silver_prior_arch_20261014/models/gen6/`. Model hashes: `MODEL_SHA256SUMS`; files in
  `/mnt/project-files/silver-az-mlp/gen6/model/`. The pack (sha 7efd43f0…) is on the never-merge
  branch `claude/silver-gen6-gpu-data`.
