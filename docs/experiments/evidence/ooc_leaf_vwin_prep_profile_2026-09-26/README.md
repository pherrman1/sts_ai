# OOC leaf `v_win` preparation profile (issue #338)

## Question

Where does native OOC-MCTS leaf-value CPU go — rich feature construction,
`v_win` tree inference, or surrounding copies — and does parent→child
prepared-feature reuse or an exact-state `v_win` cache pay off end to end?

## Configuration

- Source baseline: `8ce8565a38500b49a23372c926b9c6d5e6130d9a`.
- One seed, `12002032`, Ironclad A0, project-fair, keys off, stop after Act 3,
  Silver 10k, OOC MCTS 2,048 sims, V4 leaf policy, native leaf value, zero
  leaf combats, one thread. Command: [`run.sh`](run.sh) (pass absolute output
  prefixes), through `tools/seed_guard.sh`, `STS_OOC_CPU_PROFILE=1`.
- `v_win`: `models/v_win_trees.txt` SHA256
  `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`.
- CTM: `combat_transition_near_full_except_smoke_v2.native` SHA256
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- V4: `ooc_strategic_tok_final.native` SHA256
  `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.
- Release `one_combat` builds (SHA256):
  - `base` (baseline source): `d2dfd070…0cc3`
  - `nocopy` (adopted change): `fc1c3935…112d`
  - `cache` ([`cache_variant.patch`](cache_variant.patch), rejected): `2282c44f…9635`
  - `dup` ([`dup_variant.patch`](dup_variant.patch), census only): `1614e182…da92`
- Cloud container, 4 vCPU; ~3x slower per call than the 2026-09-23 profile
  machine. `base1`, `nocopy1`, `dup1` ran alone; `base2` and `cache1` ran
  concurrently as a pair.

## Results

All five runs produced identical result rows (floor 50, act 3, death in
combat 22) and identical non-timing MCTS trace columns (139 decisions, 119,814
simulations, 119,547 leaf evaluations, 115,071 transition samples).

| Run | MCTS CPU | `leaf_value` calls / CPU / µs per call | `leaf_features` µs | `leaf_predict` calls / µs |
| --- | ---: | ---: | ---: | ---: |
| base1 | 208.13 s | 119,520 / 14.85 s / 124.2 | — | — |
| base2 | 209.00 s | 119,520 / 14.26 s / 119.3 | — | — |
| nocopy1 | 208.08 s | 119,520 / 14.39 s / 120.4 | 3.7 | 119,520 / 115.0 |
| cache1 | 208.27 s | 119,520 / 14.37 s / 120.2 | 5.8 (incl. key) | 105,119 / 127.0 |

- Native leaf value is ~7% of MCTS CPU. Of that, feature construction is
  3.7 µs/call (0.44 s, **0.2% of MCTS CPU**); tree inference is 115 µs/call
  (13.7 s, 6.6%). The removed `GameContext`+map copy was ≈4 µs/call.
- Exact repeated feature vectors (`dup1`): 19,997 of 119,520 calls (16.7%),
  all within a 4,096-call window. A per-decision exact cache hit 14,401
  (12.0%) but `leaf_value` CPU and MCTS CPU did not change beyond run-to-run
  noise (base1 vs base2 already differ by 0.9 s MCTS / 0.6 s `leaf_value`);
  per-call inference got slower on misses. **Inference:** the ~0.5 MB key
  map competes with the ~1 MB tree ensemble for cache.

## Decision

- Adopt the copy removal and `leaf_features`/`leaf_predict` buckets: exact
  parity, simpler code, measured sub-noise saving.
- Do not implement parent→child incremental features: the maximum possible
  saving is 0.2% of MCTS CPU.
- Do not adopt the exact `v_win` cache: no measurable end-to-end gain.
- Leaf cost is model inference; it belongs to #334 (model form / batch-1
  latency), not to feature preparation.

## Limits

One seed, one repetition per arm (two for base). The 0.2% copy saving is
below this design's noise floor and is claimed only as a cost removed, not a
measured speedup.
