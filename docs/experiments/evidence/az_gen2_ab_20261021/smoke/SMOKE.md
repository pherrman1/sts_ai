# Pre-freeze smoke, 2026-10-21

Code c420dc7a, which is this branch merged with main afce2f45. Binary `one_combat` sha256 `54cb6200…`.
`run_unit.sh` ran as committed. Seeds 111149990–111149991 are smoke-only, outside the campaign block.

- All 4 arm runs finished with rc 0. Footers had `complete` and `integrityPassed`, and all four banner checks passed:
  - learned OOC stop;
  - Act-4 CTM model;
  - `[heart1] loaded`;
  - `fast_root_cap=1024`.
- The real-combat banner reads "learned stop gbt-0cac7cc64364; exact root budgets".
- Policy rows carry `root.fastRootCap`. Seed 111149990 arm B: 72 searched roots, 11 of them full-budget.
- Wall time, A / B, both seeds ran in parallel on 4 CPUs:
  - 111149990: 866 / 562 s, both died in Act 3 (floor 51 / 50);
  - 111149991: 622 / 623 s, both died in Act 2 (floor 33).
  - Gen 1b's A/B averaged ~1,480 s per run, but these two seeds are short runs, so this is no speed estimate.
- The freeze rebuilds on the freeze commit and re-smokes on new seeds.

## Frozen-binary smoke (2026-10-21, after the freeze)
Code main `844bd923`, binary `23a09099…` (v3 preset), `run_unit.sh` as at RUN_COMMIT `712d4def`. Seeds 111149992–993.
All 4 arm runs rc 0 with all banners (learned OOC stop, Act-4 CTM, `[heart1] loaded`, `fast_root_cap=1024`, learned
Silver stop gbt-0cac7cc64364); `STS_SILVER_PRIOR_PLAYOUT_ELITE=0` in the env. Both arms killed the Heart on both seeds
(floor 56). Wall A/B: 111149992 1,368 / 1,230 s; 111149993 1,101 / 1,071 s. `analyze.py` on them: 2 seeds, 2 valid.
