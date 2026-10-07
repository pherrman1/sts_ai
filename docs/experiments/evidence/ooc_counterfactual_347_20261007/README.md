# #347 OOC counterfactual: chest rule and campfire fallback (2026-10-07)

Frozen plan: [PLAN.md](PLAN.md) (independent pre-run review clear). Ledger §390; PR #429.

- Diagnostic build `1911f044` (research flags on `1ed47e5c`, #417 mechanics),
  binary SHA-256 `6fa4bf5c…5ff51677`. Run `run.sh` on one 4-CPU cloud
  container, 11:20–11:35 UTC; all eight sources `VALID`, exit 0.
  `analyze.py run ../ooc_divergence_347_20261007/run --out report.json`
  reproduces [report.json](report.json) (M/F rows there are identical to #428).
- Pre-run checks: flags off reproduces the frozen #428 `M-48000024-a2` rows and
  trace exactly; mismatched flags are refused for both schemas.

## Result

Primary verdict **`CAMPFIRE_CHAIN_INCONCLUSIVE`**: CR 13/32 vs C 9/32, net +4
(rule needs >= +8), per-seed net +4, 0, +1, -1.

| seed | M (#428) | C | CR | F (#428) |
|---|---:|---:|---:|---:|
| 48000024 Champ | 0 | 2 | 6 | 8 |
| 48000014 Donu & Deca | 1 | 1 | 1 | 8 |
| 48000116 Champ | 0 | 0 | 1 | 8 |
| 48000095 Time Eater | 0 | 6 | 5 | 5 |
| total /32 | 1 | 9 | 13 | 29 |

Descriptive (same planner seeds, different build lineage): C vs M net +8
(48000095 +6, 48000024 +2); F still beats CR by net +16.

## Why the fixes recovered little

- **Chests open, but OOC MCTS then leaves the relic.** The rule fired at all 11
  chests in each arm (no Cursed Key anywhere), yet on the reward screen that
  follows MCTS took the gold and left the relic at 8 of 11 chests in C and 7 of
  11 in CR (for example Calipers and Bag of Marbles on 48000024, Whetstone, Maw
  Bank and Smiling Mask on 48000014, Meal Ticket and Potion Belt on 48000116).
  No sapphire key was taken (keys off).
- **The ordinary chain also rests at full HP in these trajectories.** In CR
  every campfire went to the chain, which still made no-op full-HP rests 9
  times (C: 8) and smithed only 6 times over 27 campfires; on its own flat10k
  trajectories (§389) it smithed 22 of 28. **Inference:** the chain's campfire
  choice depends on the reached state, so handing campfires to it does not
  restore the flat10k upgrade path.

Four selected failure-enriched seeds, one OOC trajectory per arm and seed; the
8 reps replicate only boss-combat planner noise. Not a win-rate estimate.
