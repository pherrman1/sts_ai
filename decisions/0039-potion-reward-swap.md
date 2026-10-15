# ADR-0039: Reward potions replace the worst held potion when slots are full

Date: 2026-10-15
Status: accepted

## Context

Our engine offers a reward potion only while a slot is free
(`getAllRewardActions`). Three out-of-combat policy paths copied that rule:
`collectFreeOocReward` (the run driver's default chain), `oocTreeRuleStep` (OOC
MCTS tree rules) and `ScumSearchAgent2::stepRewardsPolicy`. With full slots,
every reward potion was left behind. The game lets the player discard a held
potion and take the new one. Only the OOC semantic layer (`DISCARD_POTION`, used
by the live advisor and OOC MCTS candidates) could do that.

The heart1 adapter's parity check (PR #552) surfaced the difference. On
2026-10-15 Philipp asked for a fix ("We skip a potion reward if we have full
potions? We need to fix that.") and, asked how to choose the potion to drop,
picked "Learned ranking" (fit per-potion values from existing fight data).

## Decision

- `search::potionRewardAction` (`src/sim/search/PotionRewardPolicy.cpp`) is the
  potion step for all three paths.
- With `STS_POTION_REWARD_SWAP` unset:
  - With a free slot, the policy takes the best-ranked reward potion.
  - With full slots, it discards the worst-ranked held potion when the best
    reward potion outranks it strictly, then takes the reward.
- The ranking is `potionKeepRank`, fitted by `tools/potion_keep/` on existing
  CTM corpora: 606,639 A20 fights (`ctm-a20/stage1`, setup `none`) and 427,847
  A0 fights (`ctm-pathb`). Per fight, the outcome is the HP plus max-HP change.
  It is regressed on held-potion counts at fight start, with run-seed and
  encounter fixed effects and HP, max HP, floor, deck size, relic count and
  gold as controls. A death linear-probability model uses the same design. A
  potion's value is `hp - 53 * death` (53 = `SilverEvalWeights::winBonus`),
  averaged over the two ascensions (Spearman 0.95 between them). Potions held
  in fewer than 200 fights (other classes') are not fitted and rank below all
  fitted ones.
- The values are observational. They measure holding the potion under Silver's
  use policy and the deployed pickup policy. Seed fixed effects remove run-level
  strength, but potion choice within a run can still be confounded.
  **Unverified** as a causal value. Smoke Bomb's value counts the HP an escape
  saves, not the rewards it forfeits.
- With Sozu, the pickup stays legacy, because a pickup obtains nothing.
- `STS_POTION_REWARD_SWAP=0` restores the legacy pickup exactly: reward potion 0
  while a slot is free, nothing otherwise. `1` equals the default. Other values
  are fatal.
- Out of scope: shop potions (the planner still never buys them), drinking Fruit
  Juice and Blood Potion out of combat, and the heart1 adapter's own choices.

## Consequences

- Runs that reach a reward screen with full slots, or with several reward
  potions, can play differently. Earlier results need `STS_POTION_REWARD_SWAP=0`
  to reproduce.
- The flag is not part of the OOC policy identity.
- **Unverified:** the playing-strength effect. The default is Philipp's decision
  (2026-10-15); no game test was run for it.

## Evidence

`tests/potion_reward_swap_test.cpp` (ctest `potion_reward_swap`) covers a swap,
a refused swap, best-first pickup and both legacy cases. The fit tables are on
the project share in `potion-keep-values/`: `a20-fit.csv`, `a0-fit.csv` and
`values.csv`. The A20 fit has seed-cluster bootstrap SEs (12 replicates; HP
coefficient SE at most 0.2).
