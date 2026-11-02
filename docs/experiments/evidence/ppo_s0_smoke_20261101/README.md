# PPO S0 smoke trajectories (2026-11-01)

`cov8.jsonl.gz`: `STS_OOC_HEART1_PPO_TRAJ` output (schema `heart1-ppo-traj-v1`) of 8 A20 games, seeds
111388903-111388910 (smoke block, seed guard), heart1.bin (export sha256 1e92f2a6…), temperature 1, Silver 1,000 in
the X1 F1000 environment (`cheap_combat_proxy_20261031/run_unit.sh`), binary from #944 head 71f2c91. 977 decision
lines, 0 fallbacks, 3 Heart kills (smoke only, not an estimate). Uncompressed sha256 prefix 4bb45f3980c3ea54.

Used for the #944 coverage tally and log-prob parity and as the replicated input of
`tools/heart1/ppo_train.py bench` (GPU update time, #945).
