# ADR-0050: Real boss and elite fights use prior-argmax Silver playouts

Date: 2026-10-18
Status: accepted; elite rooms superseded by [ADR-0056](0056-silver-prior-playout-boss-only.md)

## Context

§540 and §541 (PR #666) tested Silver playouts in which every `PLAYER_NORMAL` step plays the root prior's argmax over
card plays and END_TURN (`RolloutConfig::prior`; no potions; card selects stay greedy), against production greedy
playouts. §541 used 768 paired A20 fights (8 workers) with the gen-6 E prior and root table:

- `priorpl10000` vs greedy 10k: score +3.28 [−0.58, +7.16] NOT_SHOWN, HP lost −0.70 [−1.19, −0.22] BETTER, 7.29x CPU
  per fight. Bosses +12.55 [−0.87, +26.57] score, elites +2.89 (HP lost −0.74 [−1.43, −0.03]).
- `priorpl2500`: score +1.98 NOT_SHOWN at 1.90x CPU per fight; bosses +9.77 [+0.95, +18.64], elites +0.11.

The boss and elite numbers are descriptive subsets, not pre-registered tests. On 2026-10-18 at 19:27Z Philipp wrote:
"merge 666. keep the prior rollout for boss and elite only."

## Decision

- Real Silver fights in boss and elite rooms (`gc.curRoom` BOSS or ELITE: burning elites, Act 4's Shield and Spear,
  the Heart and the second A20 act-3 boss included) use prior playouts by default, at the unchanged simulation budget.
  Normal fights and event fights (Colosseum, Mind Bloom and other EVENT rooms) keep greedy playouts.
- It applies only when the root prior applies to every fight: `STS_SILVER_ROOT_PRIOR` is set and
  `STS_SILVER_ROOT_PRIOR_SCOPE` is not `override`. The playouts score with the model `STS_SILVER_ROOT_PRIOR` names, the
  same net as the combat's root and tree prior (Philipp, 2026-10-18 20:19Z: "always use the same prior we use for the
  combat itself"); under ADR-0049 A20 configurations set it to g7f_E. In those playouts the root prior's argmax, not the
  ADR-0046 root table, picks card plays; card selects still use the greedy agent.
- A search with a rollout, root-prior or prior-net override keeps its own setting, as the whole-run tree prior does.
  That covers research arms, `ctmsilvergen` source runs and controls, the selective-Silver and synthetic generators,
  and imagined OOC MCTS fights: `playImaginedCombatWithSilver` forces greedy playouts, as Philipp asked on 2026-10-18 at
  15:03Z ("Fallbacks should not use the prior rollout").
- `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` restores greedy playouts everywhere. When the default is on, the Silver leaf
  specification records it as `"prior_playout_rooms": "boss,elite"`.
- The live advisor is unchanged. It runs no root prior.

## Consequences

- Every A20 run that sets a root prior plays boss and elite fights differently from §541's control. Comparisons with
  earlier runs need `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`.
- CPU: boss and elite decisions go from about 0.12-0.15 s to 0.45-1.1 s (independent review measurement). The
  reviewer's Act-1 A20 run took 362 s wall instead of 311 s (+16%); in full runs with OOC MCTS, where real combat is
  2-3% of CPU (A20 profile), the share is smaller (**Inference**).
- Teacher and specification JSONs written before this ADR record no `prior_playout_rooms` and are refused by the
  `silver_leaf` equality check once a run with a root prior records it. AZ and CTM data generation must regenerate them
  or set `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`.
- The playing-strength effect at run level is not established. §541 measured fights with g6_E as root prior and root
  table; ADR-0049 A20 configurations use g7f_E. The Act-4 subset was 17 fights.
