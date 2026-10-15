# 64-rollout sibling-leaf capture and CPU value net (§490, 2026-10-15)

Label capture for a CPU value net that distills rollout3 (follow-up to §489; Philipp chose "64-rollout labels" on the
decision card at 20:28Z and "32 workers" at 21:03Z). Play is the §486 `v4` A20 arm; `STS_OOC_SIBLING_CAPTURE` with
`_EVERY=2`, `_REPEATS=64`, `_LONG=0`, `_MAX_DEPTH=2`, `_MAX_LEAVES=128` and heart1 annotation (extras in forked
children; play unchanged).

- Run commit `12b7a055` (this branch; `STS_OOC_SIBLING_REPEATS` cap raised 16 → 256), binary sha256
  `992f5cdc…e0b6`, heart1.bin `1e92f2a6…563f`.
- Seeds: A20 110000000–110000063, 32 cloud workers × 2 seeds (`worker.sh setup|run|status W`; unit runner
  `../ooc_sibling_leaf_capture_20261015/run_unit.sh`). Pre-launch review PASS. All 64 units rc=0; worker 1's container
  restarted and reran 110000000 whole. Unit wall time 7–41 min (median 21), 21.2 unit-hours.
- Smoke: 74072240, same settings and binary (`smoke_74072240.done`): rc=0, 13.4 min, 2,440 leaves, every leaf with 64
  repeats, no extra errors.
- `worker_tars.txt`: sha256 of the 32 worker tars, all verified and extracted from the lead container. Raw captures
  (149 MB) are on the project share at `/mnt/project-files/leaf-value-64/wWW.tar.gz`, not in the repo.
- `signal64.json`: `../ooc_sibling_leaf_capture_20261015/sib_signal.py` on all 64 seeds (225k leaves).
- `tv_within_x2b.{log,json,json.pt}` and `tv_within.{log,json,json.pt}`:
  `../ooc_sibling_leaf_capture_20261015/train_value.py --within [--x2b] --epochs 20` on all 64 seeds; held out
  seeds % 4 == 3 (16 seeds, 57.0k leaves). The `.json` blocks and `.pt` weights are the epoch with the best held-out
  correlation (selected on the held-out set; the logs give every epoch). Screen ids in `byParentScreen`:
  1 event, 2 rewards, 3 boss relic, 4 card select, 5 map, 6 treasure, 7 rest, 8 shop.
