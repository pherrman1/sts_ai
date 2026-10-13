# §453 evidence: plain Silver 6k vs tree prior K=8 (CPU-matched)

- [PREREG.md](PREREG.md), [worker.sh](worker.sh), [env.sh](env.sh): the frozen run
  (16 workers × 4 shards × 2 seeds, seeds 84000200–84000327), frozen at review PASS
  on run commit 94110b53.
- `RUN_GIT_SHA` (code) and `BINARY_SHA256` (preset `linux-gcc-release`).
- [result.json](result.json): output of
  `python3 tools/analyze_silver_tree_prior_452.py result.json <extracted tars>`.
- `TAR_SHA256`: sha256 of each worker tar. Raw data:
  `/mnt/project-files/silver-cpumatch-453/w01.tar`…`w16.tar` + `wWW.DONE.txt` (each
  holds `cpumatch-out-wWW/shard{0..3}.{states,arms,samples}.csv`, manifests and logs).
  The coordinator verified every tar against its DONE file from a second container.

Seeds used: 84000200–84000327 (run), 84009002 (smoke).
