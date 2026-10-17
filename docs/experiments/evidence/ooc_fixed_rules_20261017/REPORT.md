# Fixed OOC rules before and inside the search (§511, 2026-10-17)

Question (Philipp, 2026-10-17 16:10Z): should the fixed rules that run before the OOC search be rethought now
that the stack takes keys? The key rules (`heartKeyAction`, ADR-0041) belong to the separate keys thread; this
report covers the other rules and their ordering.

## Rules and order

Live driver (`run_driver.cpp` ~527-541): `heartKeyAction` → `openTreasureChestRuleStep` → `takeRewardRelicRuleStep`
→ `oocTreeRuleStep` (with `STS_OOC_MCTS_TREE_RULES`, default on by ADR-0031) → Match and Keep → OOC MCTS.
`oocTreeRuleStep` runs the same key, chest and relic rules, then takes gold, picks up or swaps potions
(`potionRewardAction`, ADR-0039), and leaves an empty reward screen. It also runs at the root, inside the tree
and in rollouts.

## Evidence 1: rule firings on the §503 A20 corpus

1,408 open §503 runs (TRAIN 1,088 + VALIDATION 320; SEALED-confirm not opened), student C prior
(`STS_OOC_MCTS_PRIOR=heart1`), keys on. `rule_firings.out`:

| Rule | Firings | What it takes from search/prior | Verdict |
| --- | ---: | --- | --- |
| Key rule | 4,778 | keys thread | keys thread |
| Open chest (no Cursed Key) | 3,380 | nothing (free) | keep |
| Take reward relic (all but 7 reviewed) | 10,077 | relic skip | keep |
| Gold | 30,148 | nothing | keep |
| Potion pickup, free slot | 13,158 | which potion if several | keep |
| Potion swap by rank, full belt | 1,452 | which potion to drop | keep |
| Leave empty reward screen | 4,439 | nothing | keep |

- Relic rule: heart1's own convention (`takeFreeRewards`, `heart1_policy.cpp:399`) also takes every reward relic
  unless a key is on the screen, so the rule agrees with the prior's training convention.
- The 7 reviewed relics go to search (`reviewed_relics.out`): left 291 of 749 offers (Juzu 95/158,
  Bottled Lightning 65/116, Bottled Flame 73/152, Unceasing Top 30/81, Bottled Tornado 22/103, Tungsten Rod 5/77,
  Dead Branch 1/73). Philipp chose to have search decide these; no change proposed.
- Audit finding #6 (Fairy ranked below Fruit Juice and others): the swap rule dropped a Fairy 4 times in
  1,408 runs. Real, but rare.

## Evidence 2: search undoes the potion rule

When the belt is full and no reward potion outranks the worst held one, the rule declines. The REWARDS root then
has "discard potion" candidates. Student C has no discard action, so under the plain heart1 prior every such root
had a uniform prior (`discard_roots.out`): 1,281 roots in 553/1,408 runs. Their picks: discard 505, leave 429,
card 255, skip card 86. Every discard was followed by taking the reward potion; 455/505 swapped to a lower-ranked
potion (mean −1.32 rank points, `search_potion_swaps.out`). 171 of the "leave" picks left a card reward untaken.

## Evidence 3: PR #591 (heart1full) smoke

PR #591 head `7fb7933`, 22 A20 seeds per arm (111155002-023), 128 sims, otherwise the §503 environment
(`smoke591.sh`). Old prior (`STS_OOC_MCTS_PRIOR=heart1`) vs default heart1full (`smoke591.out`):

- Discard roots that also offer cards now get heart1's prior (discards at its lowest logit): 9 of 19 discard
  roots, and every pick on them was the top-prior choice or tied with it.
- After the card is taken, the remaining "leave or discard" root stays uniform (10 of 19), and search discarded
  there 6 times in 22 runs.

## Change and smoke

`STS_POTION_REWARD_DECLINE_LEAVE=1` (research option, default off): in `oocTreeRuleStep` a declined reward potion
counts as nothing left, so such a screen is left by the rule. Off is the old code path. Unit test
`potion_reward_swap` and adapter self-test `ooc_mcts_adapter` pass.

Smoke on main + change (`smoke_decline_leave.sh`), plain heart1 prior, 16 A20 seeds per arm (111155024-039):
off had 1 cards-less discard root, on had 0, and the rule left 2 such screens. Discard roots with cards remain
under the plain prior (heart1full covers those). Outcomes 1 vs 1 wins, 4 vs 4 runs reaching Act 4: a smoke, not
an A/B.

## Recommendation

- Keep chest, gold, leave, relic and swap-rank rules as they are.
- Ordering: if Sapphire becomes a search decision, the relic rule must stand down while a Sapphire is offered,
  or it takes the paired relic first. The keys thread is adding this (`STS_KEY_SAPPHIRE=policy`).
- Potion: with #591 merged, the only remaining gap is the cards-less leave-or-discard root; the new option closes
  it. **Inference:** the effect is about one swap to a slightly worse potion per three runs, far below what an
  A/B could detect; making it default is Philipp's call, not a measured gain.

Seeds used: 111155000-111155039 (000-001 failed at startup with a 2,000-sim Silver budget; no gameplay).
