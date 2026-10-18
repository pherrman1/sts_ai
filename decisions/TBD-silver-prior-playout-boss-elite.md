# ADR-TBD: Real boss and elite fights use prior-argmax Silver playouts

Date: 2026-10-18
Status: accepted

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

- Real Silver fights in boss and elite rooms (`gc.curRoom` BOSS or ELITE; Act 4's Shield and Spear and the Heart
  included) use prior playouts by default, at the unchanged simulation budget. Normal fights keep greedy playouts.
- It applies only when the root prior applies to every fight: `STS_SILVER_ROOT_PRIOR` is set and
  `STS_SILVER_ROOT_PRIOR_SCOPE` is not `override`. The playouts score with that model.
- A rollout override keeps its own setting. That covers research arms and imagined OOC MCTS fights:
  `playImaginedCombatWithSilver` forces greedy playouts, as Philipp asked on 2026-10-18 at 15:03Z ("Fallbacks should
  not use the prior rollout").
- `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` restores greedy playouts everywhere. When the default is on, the Silver leaf
  specification records it as `"prior_playout_rooms": "boss,elite"`.
- The live advisor is unchanged. It runs no root prior.

## Consequences

- Every A20 run that sets a root prior plays boss and elite fights differently from §541's control. Comparisons with
  earlier runs need `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`.
- A boss or elite fight costs about 7x the CPU at a 10k budget. Real combat is 2-3% of A20 run CPU (A20 profile), so
  the run-time cost is small (**Inference**, not measured).
- The playing-strength effect at run level is not established. §541 measured fights with the gen-6 E prior; production
  now uses gen-7f E (ADR-0049). The Act-4 subset was 17 fights.
