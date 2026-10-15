# §453 pre-registration: plain Silver 6k vs tree prior K=8 at 2k (CPU-matched)

Written 2026-10-12 before any non-smoke seed was run. Philipp chose "Run check"
on 2026-10-12 22:49Z after §452.

## Question
§452: at equal 2k simulations the in-tree v1 prior (K = 8) beat plain 2k by
+1.17 fight score [+0.53, +1.79], but cost 2.9x the CPU per fight. Does it
still beat plain Silver given the same CPU? Only then is prior-guided search a
stronger teacher per unit of compute, which an AlphaZero-style loop needs.

## Design
Same harness, metric, source runs and pairing as §452
(`../silver_tree_prior_20261012/PREREG.md`), with
`STS_CTMSILVER_ARMSET=cpumatch453`. Arms per fight, 2 replicates each, combat
RNG redrawn per (fight, replicate) identically for all arms: `plain2k`,
`tree8_2k` (K = 8, w = 400, as §452) and `plain6k`. 6k was chosen because
§452 measured tree8 at 2.9x plain 2k CPU per fight; the smoke ratio is in the
PR. Seeds 84000200–84000327 (16 workers × 4 shards × 2 seeds;
seed = 84000200 + 8(W−1) + 2i and +1). Smoke used 84009002 (28 fights, control 28/28; CPU per fight plain2k 0.46 s, tree8 1.60 s, plain6k 1.52 s).
Code commit and binary: `RUN_GIT_SHA`, `BINARY_SHA256` in this folder.

## Decision rule (primary: tree8_2k − plain6k, all fights, score)
- `TREE_PRIOR_HELPS` if the CI lower bound > 0: the prior beats plain search
  at matched CPU → write an iteration-1 loop design for Philipp.
- `TREE_PRIOR_HURTS` if the CI upper bound < 0.
- `NOT_SHOWN` otherwise: the §452 gain is not shown beyond what the same CPU
  buys plain search; no loop.

Also reported: mean CPU per fight per arm (if plain6k's CPU differs from
tree8's by more than 20%, say so in the interpretation), tree8 − plain2k
(replication of §452), plain6k − plain2k, deaths, boss and elite subsets.
Tool: `tools/analyze_silver_tree_prior_452.py` (picks this primary when a
plain6k arm is present).
