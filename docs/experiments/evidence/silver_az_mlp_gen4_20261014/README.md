# Silver AZ MLP prior, generation 4 (10k teacher; self-play data and offline training)

Ledger §465. Generation 4 of `/mnt/project-files/silver-az-mlp/PLAN.md`: the teacher moves from
2k to 10k flat exact Silver (Philipp, 2026-10-13 22:04Z: try a bigger net first; if it gives
nothing, a 10k teacher on 4 workers). Full numbers: `RESULT.md` (copied from the share).

- Frozen: `FROZEN.md`, `BRIEF-worker.md` (sha 9616c3b4), `worker.sh`, `env.sh`; main `f73e6ad7`,
  binary `b4586cfc…` (`BINARY_SHA256`), prior gen 3 (`f57b7fdd…`), K = 8, weight 400, root bonus off.
- Seeds: natural 91000000-91000511, perturbed 91001000-91001511, 4 workers. 255/256 units rc 0;
  unit natural-91000228 lost to an endless `SilverSearcher::rolloutToEnd` loop (backtrace
  `w03-hang-91000228.txt`), not rerun.
- Training (`PLAN-train.md`, written before data): warm start from gen 3; run B (40 epochs,
  patience 8, LR halving, dropout 0.35) selected. `train-runA.json`, `train-runB.json`;
  `train-h512-scratch.json` is the descriptive 512/256 net.
- Parity: `g4parity_*.json` (pass). Model hashes: `MODEL_SHA256SUMS`; files in
  `/mnt/project-files/silver-az-mlp/gen4/model/`.
