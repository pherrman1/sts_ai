# Per-fight and per-root Silver search parameters (ledger-06 §526, 2026-10-17)

- Part 1 (per fight, §518 data): `part1/build.py` extracts per-redraw fight scores from the §518 tars
  (`/mnt/project-files/silver-widening-518/w0{1..8}.tar`, extracted to `<dir>/w<N>/out`; the script reads
  `/tmp/claude-0/x518/w*/out` and writes `/tmp/claude-0/x518/an/rep.csv`, edit those paths to rerun), and `part1/an.py`
  analyzes `rep.csv` (output `part1/offline_518_output.txt`). `per_fight_518.csv` on the share holds the same fights
  as redraw means only.
- `run_pilot.sh OUT TOTAL BASE EVERY`: 4 shards of `ctmsilvergen` with `STS_CTMSILVER_ARMSET=rootregret` at A20 (§518 environment).
  Run: `run_pilot.sh ~/rr-smoke 4 111193550 6` and `run_pilot.sh ~/rr-pilot 48 111193554 2` at code `80530a06`
  (main `ff0143e8`, before ADR-0046). To reproduce on later main, `STS_SILVER_ROLLOUT_ROOT_TABLE=0` is needed; the script
  sets it when the source carries the ADR-0046 default. `ONE_COMBAT=<binary>` overrides the build path.
- `split_ref.py DIR...` (primary, from the post-merge review): each half of the replicates is scored against its own 20k
  reference, so reference noise cannot make the halves agree (`split_ref_output.txt`).
- `analyze_roots.py DIR...`: regret against the pooled reference, heterogeneity and cross-fit oracle with one shared reference
  (an upper bound, see §526), LightGBM selector on decision-time features, act x room table (`analyze_output.txt`).
  `feature_check.py DIR...`: selector with the base search's visit share added (`feature_check_output.txt`).
- Raw data: `/mnt/project-files/learned-search-params/rr-root-regret.tar` (sha256 `45aecaac1d7d994c80db688ef603b6f8c12fe5df8655e93b654d90d6b67c18a9`),
  with `rr-pilot/`, `rr-smoke/` and the probe-isolation check `rr-iso/` (seed 111193552 with probes off).
