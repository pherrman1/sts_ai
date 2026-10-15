# §489 sibling-leaf capture: learned leaf values vs rollout3 (A20, 2026-10-15)

- Capture option `STS_OOC_SIBLING_CAPTURE` (code d4e3c223), run commit 8df8b9b7, binary sha256 `6eded1e2…` (`run_unit.sh`,
  `worker.sh`); heart1.bin `1e92f2a6…`. Seeds 109000000–015 lead container, 109000016–063 eight workers
  (`worker_tars.txt`; tars with the raw `*.sib.jsonl` in the project share `leaf-value-gate/`: `w01`–`w08.tar.gz` for
  109000016–063 and `lead.tar.gz` for 109000000–015; not in git).
- Metrics: `sib_signal.py` (within-parent, noise-corrected corr with E[rollout3]) → `signal64.json`;
  `sib_metrics2.py` (pair concordance, top-action agreement) → `metrics64.json`; `train_value.py` (CPU value net,
  held-out seeds % 4 == 3) → `tv_within_x2b.json` / `.log`. That run reported
  its last epoch: the `bestValNegCorr` field holds the last epoch's validation MSE (a selection bug since fixed in
  `train_value.py`); its `all`/`byParentScreen` blocks are the epoch-12 results.
