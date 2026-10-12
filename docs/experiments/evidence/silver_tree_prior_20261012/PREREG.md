# §452 pre-registration: Silver tree prior, fight-level paired pilot

Written 2026-10-12 before any non-smoke seed was run. Philipp asked for it on
2026-10-12 21:33Z (16 workers × 4 cores, 128 pairs, K = 8; fight-level
comparison instead of whole runs).

## Question
The v1 Silver prior (§397, §406) acts only at the root. Does applying it inside
the tree make a 2k Silver search play fights better than plain 2k? If yes,
prior-guided search could be a stronger teacher than plain search, which an
AlphaZero-style loop would need.

## Intervention
`SilverSearcher::nodePrior` (research only, off by default): a non-root decision
node with at least K simulations is scored once by the v1 prior; its visited
edges get the root bonus `w * P / (n + 1)` (w = 400, as §406); wherever a prior
is known (root included), untried edges are tried in descending prior order.

## Design
- `one_combat ctmsilvergen N 0 OUT SEED teacher.json 2` with
  `STS_CTMSILVER_ARMSET=treeprior452`, A0, project-fair, flat exact budgets.
- Source: one exact-10k plain-Silver run per seed with the production V4 OOC
  policy (env.sh). Every fight entry is captured. A control arm replays it
  (10k, no redraw) and must reproduce the source fight, or the fight is dropped.
- Arms per fight, 2 replicates each; replicate k redraws the combat RNG streams
  with a seed of (source seed, fight index, k), identical for every arm:
  `plain2k`, `root2k` (§406 root prior), `tree8_2k` (K = 8), `tree1_2k` (K = 1).
- Seeds 84000000–84000127 (16 workers × 4 shards × 2 seeds;
  seed = 84000000 + 32(W−1) + 2i). Smoke used 84009000.
- Code commit and binary: `RUN_GIT_SHA`, `BINARY_SHA256` in this folder
  (preset `linux-gcc-release`). Prior `prior-natpert.compact.txt`, sha256
  `573305c4…c6ee`.

## Metric
Per replicate fight score: 0 on death, else 53 + curHp + 11·potions + 0.25·gold
+ 2·maxHp (Silver's victory weights; turn and escape terms omitted). An arm's
fight score is its replicate mean. Contrast = mean over valid fights of the
paired per-fight difference; 95% CI from a bootstrap over source seeds
(10,000 resamples, RNG seed 0). Tool: `tools/analyze_silver_tree_prior_452.py`.

## Decision rule (primary: tree8_2k − plain2k, all fights, score)
- `TREE_PRIOR_HELPS` if the CI lower bound > 0 → design an iteration-1 loop
  (prior-guided labels) and confirm at run level.
- `TREE_PRIOR_HURTS` if the CI upper bound < 0.
- `NOT_SHOWN` otherwise → no loop; close the line in the ledger.

Secondary, descriptive: root2k − plain2k, tree8_2k − root2k, tree1_2k −
plain2k (upper bound of in-tree guidance at matched sims), tree1 − tree8, death
rate differences, boss and elite subsets, mean CPU seconds per fight per arm.
No arm is matched on CPU; the smoke measured tree8 ≈ 2.5x and tree1 ≈ 9x
plain 2k CPU per fight.
