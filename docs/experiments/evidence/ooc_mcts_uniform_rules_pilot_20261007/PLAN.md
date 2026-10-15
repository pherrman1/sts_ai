# #347 uniform-prior OOC MCTS with the chest and relic rules: 32-seed pilot (plan, 2026-10-07)

Status: frozen after independent pre-run review (clear; its counter fix and
wording notes are folded in). Philipp chose "uniform
only. lets go." in the PR #429 thread (16:21 UTC), after §392 (uniform prior
22/32 vs policy prior 9/32 on the four R-seed boss entries).

## Question

How do full runs look with live OOC MCTS on a uniform prior now that every
OOC policy opens chests (no Cursed Key) and takes reward relics (except
Bottled ×3, Dead Branch, Tungsten Rod, Unceasing Top, Juzu Bracelet), and the
search can no longer take keys? Descriptive pilot, one arm, as Philipp asked;
no comparison arm is run.

## Design

- Seeds `53000000..53000031` (32, unused; not in any ledger or evidence run).
- Arm: the #417 `mcts` arm environment (`arm_env.sh` at `10e56bd8`,
  hash-checked: 2048 sims, cPUCT 1.5, early stop, screengbm leaf, flat exact
  10k Silver, adaptive and learned stopping off, `STS_FAIR=1`, keys off,
  `STS_STOP_AFTER_ACT=3`) plus `STS_OOC_MCTS_PRIOR=uniform`. The rules and the
  keys-off filter are always on in this build.
- Binary: `one_combat` `linux-gcc-release` built from `c2e701d` (the rules;
  `7421eab` only edits a comment), SHA-256
  `ee4fe043b6057b77ce654d6db68b2b0a7f8a4c628793c91e4471e7aa9cc8a1e8`.
- `launch.sh`: four shards of 8 seeds, one CPU each, through `seed_guard`,
  with `STS_OOC_DECISION_TRACE`. Smoke first: seed 53009000, act 1 only.

## Reporting (fixed before the run)

`analyze.py RUN_DIR --out report.json`: wins out of 32 with a Wilson 95%
interval, losses by act (boss floor or not), mean final floor and time, and
from the traces: chests opened by the rule, reward relics taken by the rule
and by the policy that owned the step (MCTS, chain or Match and Keep),
exception relics that policy took, non-exception relics
left behind (expected 0), campfire rests and smiths
(Toke counts as a smith; descriptive). It refuses a shard whose
logged config is not 2048 sims, uniform prior, visit selection, screengbm, or
that has a seed failure, and requires exactly the 32 seeds.

Context only, not a comparison: #417 (128 seeds, 48M, same arm with the
policy prior and no rules) won 56.3% with MCTS and 78.1% with flat10k; the
rollout3 look (§277 setting, 51M) won 25/32 with a uniform prior. Different
seeds and settings: a difference to these is not evidence. **Next**, on
Philipp's word: if this looks competitive, a paired fresh-seed comparison
against flat10k with the same rules.

## Cost

Act-1 smoke ~25 s. Full runs with the #417 mcts arm: on the order of minutes
per seed; about one hour on 4 CPUs. One container, no other threads.
