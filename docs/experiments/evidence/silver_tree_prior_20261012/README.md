# §452 evidence: Silver tree prior, fight-level paired pilot

- [PREREG.md](PREREG.md): question, arms, metric and decision rule (frozen at
  review PASS, commit 655aa915; code 17ddaa67, binary sha256 in `BINARY_SHA256`).
- [worker.sh](worker.sh), [env.sh](env.sh): the exact worker run (16 workers ×
  4 shards × 2 seeds, seeds 84000000–84000127).
- [result.json](result.json): output of
  `python3 tools/analyze_silver_tree_prior_452.py result.json <extracted tars>`.
- `TAR_SHA256`: sha256 of each worker tar. Raw data:
  `/mnt/project-files/silver-tree-prior-452/w01.tar`…`w16.tar` (each holds
  `treeprior-out-wWW/shard{0..3}.{states,arms,samples}.csv`, manifests and logs).
  The coordinator verified every tar against its DONE file from a second container.

Seeds used: 84000000–84000127 (run), 84009000–84009001 (smoke); reviewer seeds
74035000–74035004.
