# 64-rollout sibling-leaf capture (2026-10-15)

Label capture for a CPU value net that distills rollout3 (follow-up to §489, Philipp's choice of "64-rollout labels").
Play is the §486 `v4` A20 arm; `STS_OOC_SIBLING_CAPTURE` with `_EVERY=2`, `_REPEATS=64`, `_LONG=0`, `_MAX_DEPTH=2`,
`_MAX_LEAVES=128` and heart1 annotation (extras in forked children; play unchanged).

- Seeds: A20 110000000–110000063, 32 cloud workers × 2 seeds (`worker.sh setup|run|status W`).
- Unit runner: `../ooc_sibling_leaf_capture_20261015/run_unit.sh`.
- Binary sha256 `992f5cdc…e0b6` (this branch; `STS_OOC_SIBLING_REPEATS` cap raised 16 → 256), heart1.bin `1e92f2a6…563f`.
- Outputs: `/mnt/project-files/leaf-value-64/wWW.tar.gz` + `wWW.DONE.txt`.
- Smoke: 74072240 (same settings).
