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
potions? We need to fix that.") and was offered a hand-written ranking as the
recommended way to choose which potion to drop.

## Decision

- `search::potionRewardAction` (`src/sim/search/PotionRewardPolicy.cpp`) is the
  potion step for all three paths.
- With `STS_POTION_REWARD_SWAP` unset:
  - With a free slot, the policy takes the best-ranked reward potion.
  - With full slots, it discards the worst-ranked held potion when the best
    reward potion outranks it strictly, then takes the reward.
- The ranking is `potionKeepRank`, a hand-written Ironclad table. **Inference:**
  it encodes common player judgement and was not fitted or tested.
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
- **Unverified:** the playing-strength effect, and whether the ranking is good.
  A fitted ranking (for example from fight data) could replace the table later.

## Evidence

`tests/potion_reward_swap_test.cpp` (ctest `potion_reward_swap`) covers a swap,
a refused swap, best-first pickup and both legacy cases.
