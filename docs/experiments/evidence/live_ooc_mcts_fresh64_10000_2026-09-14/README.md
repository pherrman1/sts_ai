# Fresh64 fixed10000 gate evidence

The adjacent experiment Markdown records preregistration, readiness and final
outcomes. `freeze.json` separates the reviewed analysis/launch commit from the
exact remote runtime source. The two manifests freeze source/cache/binary,
models, environment, seeds and output paths. `launch_arm.py` renders these via
the unchanged repository GCP launcher with real exact-checkout cwd. Canary and
official records remain separate; only official64 paired rows enter analysis.

Reproduce offline outcome analysis from the repository root (no games):

```bash
python3 tools/analyze_ooc_mcts_gameplay.py \
 docs/experiments/evidence/live_ooc_mcts_fresh64_10000_2026-09-14/official/control.csv \
 docs/experiments/evidence/live_ooc_mcts_fresh64_10000_2026-09-14/official/treatment.csv \
 /tmp/fresh64-reproduced.json \
 --combat-sims 10000 --mcts-sims 10000 --seed-start 980000 --seed-count 64
```

Only the input-path keys differ from the original result when paths change;
input byte hashes and all outcomes/intervals/accounting must reproduce. Logs
are losslessly gzip-compressed. For `validate_run.py`, decompress the matching
logs into an external scratch copy of the official directory, then pass that
directory, arm name,980000,64. Independent review additionally checks model-load
messages, frozen full configuration/source/hash binding and zero battleLeaves.
Native benchmark-canary validation also consumes the frozen executable, whose
hash is recorded; no binary/model weights are copied into this Git packet.

`SHA256SUMS` covers packet files; `RAW_SHA256SUMS` covers original uncompressed
raw logs/CSVs/configs/metadata/support receipts. Seed inventories are prospective
freshness receipts, not samples to pool. Resource/progress snapshots are
read-only observations; timing under24-worker batches is descriptive.
