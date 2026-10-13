# §460 evidence: Silver AZ MLP prior gen 3 vs plain Silver and vs gen 1

- Pre-registration: [`PREREG.md`](PREREG.md), frozen before any eval seed was played
  (`SHA256SUMS`). The pre-launch review asked for one change before launch: a shard that
  aborts on a native Silver stall must not abort the analysis. `analyze_gen3.py` then
  excluded such fights per fight, and the PREREG gained one sentence; the delta review
  passed. Worker brief [`BRIEF-worker.md`](BRIEF-worker.md) (sha256 `24190753…5303`),
  [`worker.sh`](worker.sh), [`env.sh`](env.sh), analysis [`analyze_gen3.py`](analyze_gen3.py).
- Code: main `37b7d33e`. Release `one_combat` sha256 in [`BINARY_SHA256`](BINARY_SHA256).
  Models: gen 3 `f57b7fdd…5315` (`mlp8_2k`, also `STS_SILVER_ROOT_PRIOR`), gen 1
  `a5f4505a…64d2` (`mlp_prev8_2k`, scored entirely by gen 1 through the override net).
- Run: 2026-10-13 ~21:00-21:15Z, 16 cloud workers x 4 shards (`bash worker.sh W 16 OUT`),
  seeds 90000000-90000127, 2 per shard. All 64 shards rc = 0 with manifests; every
  source run valid; no stall.
- Raw: `/mnt/project-files/silver-az-mlp/gen3-eval/wWW.tar` (sha256 in
  [`TARS_SHA256`](TARS_SHA256), repeated in each `wWW.DONE.txt`).
- Output: [`analysis.json`](analysis.json) from
  `python3 analyze_gen3.py analysis.json w01 … w16` over the extracted tars.

## Exclusions
3,303 fights were replayed; 3,275 are valid in every arm and counted. The analyzer's
`invalid_control_replay` (28) counts every fight with any invalid arm row. By
`quarantineReason` ([`exclusions_by_reason.py`](exclusions_by_reason.py), descriptive):
- 24 fights with escape-quarantined rows only (an arm, replicate or the source fight escaped,
  e.g. Smoke Bomb);
- 4 fights with `control_state_invalid` rows plus escape rows.
- `incomplete_shard_abort`: 0.

Invalid arm rows by arm and reason: escape control 24, plain2k 47, plain_cpu 47, mlp8_2k 45,
mlp_prev8_2k 44; `control_state_invalid` plain2k 5, plain_cpu 5, mlp8_2k 5, mlp_prev8_2k 6
(228 rows; 29,727 rows in total).

Seeds used: 90000000-90000127 (run), 74057000-74057003 (implementer smoke),
74058000-74058003 (reviewer smoke).
