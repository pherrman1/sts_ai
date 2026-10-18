# ADR-TBD: The default Silver rollout root table and A20 Silver prior are gen-7f E

Date: 2026-10-18
Status: accepted

Amends: [ADR-0046](0046-silver-rollout-root-table-default.md), which named gen-6 E (`ca9bd7f2…`) as the bundled model.

## Context

Gen 7 (§517, PR #621) is the gen-6 MLP prior's training window plus 371k A20 Act-4 self-play roots (Shield and Spear,
the Heart). g7_E passed its offline gate (Act-4 fold-4 CE 1.408 vs g6_E 1.498). As the Silver prior on 1,094 held-out
Act-4 states it was NOT_SHOWN at 40k (dWin −0.3 pp [−1.6, +1.0]) and at 2.5k (−0.0 pp [−0.6, +0.6]).

On 2026-10-18 at 13:41Z Philipp asked "can you still make gen 7 the prior?". On the follow-up card (13:44Z) he chose
"Retrain, then swap": retrain on the active power features, which his 11:44Z rule requires of g7_E and later combat
nets; run a short root-table check; then switch unless it shows harm.

- Retrain: g7f_E is the same window re-featurized with `STS_ACTIVE_POWER_FEATURES=1` and trained with gen 7's recipe.
  Data branch `claude/silver-gen7-act4-data` 0168b72d, `gen7f/`. Sanity gate PASS: fold-4 CE orig 1.1731 vs g7_E
  1.1750, Act-4 1.4073 vs 1.4082. Native parity 1.9e-6.
- Check (PR #621, `docs/experiments/evidence/silver_g7f_rt_20261018/`): 1,094 held-out Act-4 states at 2.5k, 8 copies.
  Each arm used one model as both root/tree prior and rollout root table. Result NOT_SHOWN, not HARM: win 61.53% (g6_E)
  vs 62.07% (g7f_E), dWin +0.5 pp [−0.1, +1.2], over 8,752 pairs.

## Decision

- `kDefaultRolloutRootTableModel` is `models/combat_policy_mlp_g7f_E.txt` (sha256 `c45dcc0a…`). With
  `STS_SILVER_ROLLOUT_ROOT_TABLE` unset, Silver and the live advisor build the per-root rollout table with g7f_E.
- `STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g6_E.txt` restores the ADR-0046 table, and
  `STS_SILVER_ROLLOUT_ROOT_TABLE=0` restores the ADR-0040 table. Both are unchanged.
- `models/combat_policy_mlp_g6_E.txt` stays bundled for that restore and for the research harnesses that pin it.
- `tools/live_game_runtime.py` copies g7f_E into each release and pins it as `rolloutRootTableSha256`. A reinstall of the
  live runtime still waits for Philipp's word.
- A20 run configurations that set a Silver root or tree prior (`STS_SILVER_ROOT_PRIOR`) use g7f_E from now on. The
  setting stays env-only and has no code default.

## Consequences

- Every Silver search with the default root table plays differently from ADR-0046. Comparisons with earlier runs need
  `STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g6_E.txt`.
- The playing-strength effect is not established. The check covered Act-4 fights only, and both earlier gen-7 A/Bs
  were NOT_SHOWN.
- g7f_E was trained and checked with `STS_ACTIVE_POWER_FEATURES=1`, which matches the deployed default. g6_E was
  trained on legacy features.
