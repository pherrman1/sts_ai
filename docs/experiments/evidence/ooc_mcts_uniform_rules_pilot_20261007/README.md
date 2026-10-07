# #347 uniform-prior OOC MCTS with chest and relic rules: 32-seed pilot (2026-10-07)

Plan: [PLAN.md](PLAN.md) (frozen after independent pre-run review, plan
commit `d9ee73f`, recorded in `run/PLAN_COMMIT`). Ledger §393.

## Provenance and validity

- Binary `one_combat` built from `c2e701d`, SHA-256 `ee4fe043…a1e8` (hash
  checked by `launch.sh`); #417 `mcts` arm env at `10e56bd8` plus
  `STS_OOC_MCTS_PRIOR=uniform`. Seeds 53000000..53000031, four shards of 8.
- Run 16:27–16:49 UTC on one 4-CPU container (shards 13–22 min).
- All shards exit 0, no seed failures; every log shows sims=2048,
  prior=uniform, root_selection=visits, leaf_value=screengbm; all 32 seeds present.

## Result (`analyze.py run`, [report.json](report.json))

- **Wins 18/32 (56.3%), Wilson 95% [39.3%, 71.8%].** Mean final floor 44.6,
  mean 125 s per run.
- Losses (14): act 1 boss 1, act 2 boss 4, act 2 other 3, act 3 boss 4,
  act 3 other 2. Nine of 14 at a boss.
- Rules worked as intended: 93 of 93 chests opened by the chest rule; 187
  reward relics taken by the relic rule; the 10 exception relics offered were
  all taken by the owning policy anyway; no non-exception relic left behind.
- Campfires: 200 visits, 108 smiths, 81 rests, 10 with no change at full HP.

**Context only, not a comparison** (different seeds and settings): #417 won
56.3% with OOC MCTS (policy prior, no rules) and 78.1% with flat10k on 48M
seeds. **Inference:** with the rules and a uniform prior, OOC MCTS is not
visibly better than the #417 MCTS arm and still well below the #417 flat10k
rate; whether it beats flat10k with the same rules needs a paired run.
Boss losses remain the largest group.
