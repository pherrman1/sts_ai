# #347 OOC divergence on the #428 R seeds (2026-10-07)

Follow-up to #428 (ledger §388, `PREPARATION_HEADROOM_SIGNAL`: flat10k boss
entries won 29/32, OOC-MCTS entries 1/32 on seeds 48000024, 48000014,
48000116, 48000095). Question: which out-of-combat decisions made the flat10k
(F) entries stronger than the OOC-MCTS (M) entries? Ledger §389.

Descriptive replay analysis only: no new seeds, no new gameplay arm, no model
or default change.

## Provenance

- Branch base `main` `1e1bdc09`. Diagnostic build source `1ed47e5c` (parent
  `5549a16a`, the #428 build on the #417 baseline `5e9583cc`), merged into the
  task branch. It adds only `STS_OOC_DECISION_TRACE` (read-only per-step JSONL
  in `runFullRunOOC`, see `apps/one_combat/run_driver.cpp`). Binary
  `linux-gcc-release` `one_combat`, GCC 13.3, SHA-256
  `b8618e04110e4eb636f23f4eeeded40b88869767c61b6f83bd6b82c02fc956b2`.
- Sources and reps: the frozen #428 `selection.json` (copied here, from
  `689e1149`), `arm_env.sh` at #417 ref `10e56bd8` (hash-checked by `run.sh`).
- `run.sh` is the #428 runner plus one export of `STS_OOC_DECISION_TRACE`
  per source. Profile pass: same runner with `STS_RUN_PROFILE` also exported,
  M sources only ([profile/](profile/)).

## Validity

All eight sources `VALID` in both passes. Every `rows.csv` column except
`cpuSeconds`/`wallSeconds` is identical to the frozen #428 rows (96 rows), and
the decision traces of the plain and profile passes are byte-identical, so
neither trace changed a trajectory.

## Findings (four failure-enriched seeds)

Traces: `run/<stateId>.ooc.jsonl`, cut at the target boss by `align.py`;
family counts by `families.py`; root statistics by `prior_check.py`.

| seed | chests opened M / F | campfire smiths M / F | relics at entry M / F | upgrades at entry M / F |
|---|---|---|---|---|
| 48000024 | 0 of 2 / 2 of 2 | 1 of 7 / 5 of 6 | 7 / 11 | 4 / 16 |
| 48000014 | 0 of 3 / 4 of 4 | 0 of 9 / 9 of 10 | 8 / 17 | 6 / 19 |
| 48000116 | 0 of 2 / 2 of 2 | 1 of 4 / 5 of 6 | 8 / 8 | 6 / 9 |
| 48000095 | 0 of 4 / 3 of 3 | 1 of 7 / 3 of 6 | 9 / 14 | 17 / 18 |

1. **OOC MCTS never opens a treasure chest.** All 11 M treasure rooms took
   `LEAVE_TREASURE`; F opened all 11 (one relic each, gold on some). Every
   chest is free (no Cursed Key on any M path at those floors).
2. **OOC MCTS rests instead of smithing.** M chose `REST` at 24 of 27
   campfires and smithed 3 times; F smithed 22 of 28. Nine M rests were at full
   HP (heal 0: 48000014 floors 15/27/29/42, 48000095 floors 15/24/29/41/49);
   48000024 rested at 72, 75 and 78 of 80. This, plus F's Back to Basics on
   48000024, accounts for the two large upgrade gaps #428 reported (16 vs 4,
   19 vs 6); on 48000095 M reached 17 upgrades by other routes.
3. **Both follow the V4 policy prior, not the search value.** At the 11
   treasure roots the prior put 0.76–0.99 on leaving; `OPEN_CHEST` had the
   higher mean Q at 8 of 11 roots, but leaving reached the 1,025-visit early
   stop lock first. At the campfire roots `REST` carried prior 0.14–0.78 while
   each smith target got 0.01–0.08; another action had a higher mean Q than
   the chosen one at 14 of 27 campfire roots. Over all 301 multi-action M roots, the executed action was the
   max-prior action 248 times and the max-Q action 121 times.
4. Smaller, not recurring on all seeds: M skipped two relic rewards on 48000024
   (Enchiridion after paying 16 HP in Cursed Tome; Regal Pillow at an elite)
   and one on 48000014 (Lantern). Route differences: F took more elites on
   three seeds (6 vs 3, 5 vs 3, 6 vs 4); on 48000024 M never visited a shop.
5. **Earliest divergence is at Neow or floor 0 on every seed, but in a
   different family each time:** 48000024 the Neow card pick (M Blind, F
   Panacea), 48000014 the first map node, 48000116 the Neow option (M
   transforms a Defend, F takes 24 damage for a rare card, Demon Form), 48000095 the Neow
   option (M upgrades Bash, F trades 99 gold for Incense Burner). No single
   early decision recurs; chests and campfires are the families that do.

**Inference:** the strongest recurring cause in these four entries is the
policy prior steering 2,048-simulation OOC MCTS (visit-count root selection,
early stop) on low-branching room screens. Not shown causal: trajectories
diverge in RNG after the first different decision, so the chest and campfire
losses are not isolated from everything that followed.

## Not done

No counterfactual run; the proposal is in ledger §389 and waits for approval
and pre-run review. Not a win-rate estimate: four selected R seeds.
