# #347 boss-entry budget rescue on #417 sources (2026-10-07)

Frozen plan: [PLAN.md](PLAN.md). Sources: [selection.json](selection.json)
(`select.py` over the #417 rows at evidence ref `10e56bd8`), frozen before any
challenger run. Independent pre-run review: one blocking analyzer finding
(an unreached source boss counted as structural instead of reproduction-only),
fixed in `946d49d9` and confirmed. Run frozen at plan commit `946d49d9`.

- Diagnostic build source `e6b6122a` (research change `dbf6f573` applied to the
  #417 baseline `5e9583cc`). Binary SHA-256
  `5b83c7ae3d2e6e28693638ac97759b30a19b5067facbb070a1739204d4693f68`
  (`linux-gcc-release`, `one_combat`, GCC 13.3). Models as in PLAN.md.
- Selftest `bossrescue347selftest 1 48009000 1000` (flat10k arm, current-main
  build): all eight checks PASS. Smoke ([smoke/](smoke/), never pooled): both
  sources `VALID`; the mcts log shows `[live OOC MCTS ON sims=2048 ... leaf_value=screengbm`.
- Run ([run/](run/)): `run.sh` on one 4-CPU cloud container, four workers,
  04:44–04:56 UTC. All eight processes exit 0, all eight entries `VALID`.
  `analyze.py selection.json run --out report.json` reproduces [report.json](report.json).

## Validity (implementation)

Every reconstructed run matched its historical #417 row on all eight fields;
the hook saw the expected boss; each source fight was a 10k loss. Each
original-seed 10k control reproduced its source fight exactly (outcome, raw
terminal HP, full action trace, post-exit state digest, simulations). Control
and A rep-0 repeats after the other arms were identical. Every row started from
the entry digest and every searched root ran exactly 10,000 or 40,000 steps.
For the four R sources the flat10k arm had won the same seed, so their exact
reproduction under the mcts environment also shows the live MCTS policy ran.

## Result (descriptive, eight failure-enriched entries)

Verdict **`BUDGET_HEADROOM_INCONCLUSIVE`, shape mixed**: B won 13/32 vs A 12/32,
3 rescues and 2 regressions, net +1 (rule needs >= 4), positive net rescue in
2 entries (rule needs >= 3).

| entry | source arm | boss | entry HP | potions | deck (upg) | A wins | B wins | rescue / regress | first A/B divergence (action index per rep) |
|---|---|---|---|---|---|---:|---:|---|---|
| R1-48000024-a2 | mcts | Champ | 80/85 | none | 29 (4) | 1/4 | 2/4 | 2 / 1 | 4, 0, 4, 14 |
| R2-48000014-a3 | mcts | Donu & Deca | 80/80 | Gambler's Brew | 37 (6) | 0/4 | 0/4 | 0 / 0 | 4, 4, 2, 0 |
| R3-48000116-a2 | mcts | Champ | 54/85 | none | 33 (6) | 0/4 | 0/4 | 0 / 0 | 1, 31, 1, 1 |
| R4-48000095-a3 | mcts | Time Eater | 80/80 | Ancient, Swift ×2 | 41 (17) | 0/4 | 0/4 | 0 / 0 | 4, 5, 4, 5 |
| C1-48000062-a1 | flat10k | Slime Boss | 68/103 | Weak | 16 (1) | 3/4 | 4/4 | 1 / 0 | 1, 5, 3, 2 |
| C2-48000039-a2 | flat10k | Collector | 104/104 | Steel, Forge, Skill | 30 (15) | 4/4 | 3/4 | 0 / 1 | 2, 4, 1, 5 |
| C3-48000055-a3 | flat10k | Donu & Deca | 49/83 | none | 36 (17) | 0/4 | 0/4 | 0 / 0 | 1, 6, 1, 1 |
| C4-48000050-a1 | flat10k | Slime Boss | 33/85 | Energy, Gambler's, Fire | 15 (2) | 4/4 | 4/4 | 0 / 0 | 2, 2, 2, 1 |

Trace pointers: `run/<entry>.rows.csv`, rows `kind=A|B`, same `rep`; relics,
full deck and per-pair HP are in `report.json` and the rows' `postExitSummary`.

| stratum | A wins | B wins | net | entries net > 0 | entry bootstrap of mean net/entry (descriptive) |
|---|---:|---:|---:|---:|---|
| R | 1/16 | 2/16 | +1 | 1 | [0.00, 0.75] |
| C | 11/16 | 11/16 | 0 | 1 | [-0.75, 0.75] |
| all | 12/32 | 13/32 | +1 | 2 | [-0.25, 0.50] |

Raw terminal HP where both arms won (B − A, before act-transition healing):
C1 +5, −10, −17; C2 −15, −7, +27; C4 +7, −2, −6, −4. Potions left were equal in
every such pair. These survivor-only differences are not an overall benefit.

Cost (four reps per entry): A 13.36M simulations, 230 CPU-s in total; B 57.76M,
1,022 CPU-s (4.4×). At 40k the 32,768-node reuse cap discards the tree more
often: fresh roots 956 (B) vs 303 (A), reroots 488 (B) vs 1,033 (A).

## Interpretation (separate from validity)

- More search rescued little: net +1 of 32 pairs, consistent with no budget
  effect at this scale. This does not exclude combat weaknesses that more
  search cannot fix.
- Three of four R entries (two act-3 bosses at full HP, one Champ at 54/85)
  lost all eight continuations at both budgets. **Inference:** these entries
  are hard for native Silver at either budget; whether better preparation
  would win them is untested.
- Three of four C entries (C1, C2, C4) were historical 10k losses, yet fresh
  10k planner seeds won 11 of 12. **Inference:** those #417 flat10k boss
  deaths were largely planner-seed variance on winnable states, not budget-
  limited or unwinnable.
- Planner repeats share one environment; they are not independent game
  futures. Nothing here estimates full-run effects or how much of the #417
  MCTS regression is combat.

## Recommended next experiment

Preparation counterfactual on the R seeds: for 48000014, 48000024, 48000095
and 48000116 the flat10k arm won. Capture each seed's flat10k boss entry with
the same mode and replay both arms' entries with the same 10k planner repeats.
This holds combat fixed and varies only the OOC policy that produced the entry.
