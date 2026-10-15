# §455 evidence: Silver AZ MLP prior gen 1 vs plain Silver at matched CPU

- Pre-registration: [`PREREG.md`](PREREG.md), frozen before any eval seed was played
  (`SHA256SUMS`; independent pre-launch review PASS). Worker brief
  [`BRIEF-worker.md`](BRIEF-worker.md) (sha256 `2abf739e…501e`), [`worker.sh`](worker.sh),
  [`env.sh`](env.sh), analysis [`analyze_gen1.py`](analyze_gen1.py).
- Code: main `4f0cfb4c` (#517). Release `one_combat` sha256 in [`BINARY_SHA256`](BINARY_SHA256);
  model `combat_policy_mlp_gen1.txt` sha256 `a5f4505a…64d2` (`/mnt/project-files/silver-az-mlp/gen1/`).
- Run: 2026-10-13 15:00-15:20Z, 16 cloud workers x 4 shards (`bash worker.sh W 16 OUT`), seeds
  85000000-85000127, 2 seeds per shard. All 64 shards rc = 0, every source run valid (2/2 per shard),
  every binary and model hash checked by `worker.sh` and recorded in each manifest.
- Raw: `/mnt/project-files/silver-az-mlp/gen1-eval/wWW.tar` (sha256 in [`TARS_SHA256`](TARS_SHA256);
  each `wWW.DONE.txt` repeats its tar hash, `shards.txt` and the shard log tails).
- Output: [`analysis.json`](analysis.json) from
  `python3 analyze_gen1.py analysis.json gen1eval-out-w*` over the 16 extracted tars.

## Exclusions
3,423 fights (states) were replayed; 3,409 are valid in every arm and counted. The 14 excluded:
- 9 fights with escape-quarantined arm rows only (an arm or replicate escaped, e.g. Smoke Bomb);
- 5 fights whose control replay was invalid (`control_state_invalid`), which also have escape rows.
Invalid arm rows by arm and reason: escape plain2k 22, plain_cpu 22, mlp8_2k 21, control 13;
`control_state_invalid` plain2k 5, plain_cpu 5, mlp8_2k 6 (94 rows; 23,961 rows in total).

Seeds used: 85000000-85000127 (run), 74043003 (worker-script smoke).
