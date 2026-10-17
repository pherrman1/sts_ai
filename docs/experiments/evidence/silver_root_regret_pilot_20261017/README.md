# Per-root Silver search-parameter pilot (ledger-06 §526, 2026-10-17)

- `run_pilot.sh OUT TOTAL BASE EVERY`: 4 shards of `ctmsilvergen` with `STS_CTMSILVER_ARMSET=rootregret` at A20 (§518 environment).
  Run: `run_pilot.sh ~/rr-smoke 4 111193550 6` and `run_pilot.sh ~/rr-pilot 48 111193554 2` at code `80530a06`.
- `analyze_roots.py DIR...`: regret per arm, replicate heterogeneity, cross-fit oracle, LightGBM selector, act x room table
  (`analyze_output.txt`). `feature_check.py DIR...`: selector with the base search's visit share added (`feature_check_output.txt`).
- Raw data: `/mnt/project-files/learned-search-params/rr-root-regret.tar` (sha256 `45aecaac1d7d994c80db688ef603b6f8c12fe5df8655e93b654d90d6b67c18a9`),
  with `rr-pilot/`, `rr-smoke/` and the probe-isolation check `rr-iso/` (seed 111193552 with probes off).
