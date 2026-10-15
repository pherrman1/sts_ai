# #347 default-stack boss deaths: fresh-planner replays (2026-10-09)

Frozen plan: [PLAN.md](PLAN.md) (code and plan `93d0bd35`, before any seed of
this experiment ran). Ledger §417.

- Binary `one_combat` built from `93d0bd35` (`linux-gcc-release`, GCC 13.3),
  SHA-256 `a8fa3bd205d1f4aaffe5c6258e2b7740c6b52d7721fe45b1021ca4802b431f67`,
  copy at `/mnt/project-files/boss-deaths-347/one_combat-93d0bd35`.
- Environment [env.sh](env.sh): ADR-0026 live profile (V4 gate stack,
  learned-stop Silver), OOC MCTS off, Act-3 stop. Startup logs show the V4
  token net, the low-weight removal default and "learned stop".
- Smoke ([smoke/](smoke/), seeds 66009000..015, never pooled): three boss
  deaths, all `VALID` with exact control parity.

## Execution

- Stage 1 ([source_run.sh](source_run.sh), [sources/](sources/)): 256
  default-stack runs on seeds 66000000..66000255, four shards on one 4-CPU
  cloud container, all exit 0, 5,108 CPU-s. 214/256 won (83.6%); 42 losses,
  35 of them to an act boss (act 1/2/3: 1/13/21).
- Selection ([select_deaths.py](select_deaths.py) →
  [selection.json](selection.json)): all 35 boss deaths (cap 48 not reached).
- Stage 2 ([run.sh](run.sh), [run/](run/)): one `bossrescue347` process per
  entry, 1,167 CPU-s. **All 35 entries `VALID`:** each reconstruction matched
  its stage-1 row on all eight fields, the hook saw the recorded boss, the
  original-seed control reproduced the source fight exactly (outcome, terminal
  HP, full action trace, post-exit state digest, simulations), both repeats
  were identical, every row started from the entry digest and no searched
  root exceeded 10,000 steps.
- `analyze.py selection.json run --out report.json` reproduces
  [report.json](report.json).

## Result

Verdict **`MIXED`**: 15 `WINNABLE` (≥ 4/8), 14 `DOOMED` (0/8), 6 `MARGINAL`.
Neither class reaches half of the 35 entries. Mean fresh win rate 40.0%,
entry bootstrap 95% [26.4%, 53.6%]. The distribution is bimodal: 14 entries
won 0/8 and 7 won 8/8.

| fresh wins of 8 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| entries | 14 | 3 | 1 | 2 | 0 | 4 | 3 | 1 | 7 |

| boss | entries | fresh wins | doomed / marginal / winnable |
|---|---:|---:|---|
| Time Eater | 10 | 14/80 | 7 / 1 / 2 |
| Awakened One | 6 | 6/48 | 4 / 1 / 1 |
| Donu and Deca | 5 | 25/40 | 0 / 1 / 4 |
| Champ | 7 | 24/56 | 3 / 1 / 3 |
| Collector | 3 | 11/24 | 0 / 2 / 1 |
| Automaton | 3 | 24/24 | 0 / 0 / 3 |
| The Guardian | 1 | 8/8 | 0 / 0 / 1 |

By act: act 2 59/104 fresh wins (3 doomed of 13), act 3 45/168 (11 doomed of
21), act 1 8/8 (one entry).

| class | entries | mean HP / max | mean HP | deck (upgraded) | potions | act 3 |
|---|---:|---:|---:|---|---:|---:|
| DOOMED | 14 | 61% | 52 | 35.6 (11.4) | 1.5 | 11 |
| MARGINAL | 6 | 100% | 90 | 34.5 (8.0) | 1.0 | 3 |
| WINNABLE | 15 | 83% | 73 | 32.3 (9.7) | 1.9 | 7 |

Per entry (HP at boss entry, deck size with upgraded count, relics, filled
potion slots):

| entry | boss | HP | deck | relics | potions | fresh wins | class |
|---|---|---|---|---:|---:|---|---|
| D-66000005-a3 | Time Eater | 65/76 | 31 (15) | 14 | 0 | 0/8 | DOOMED |
| D-66000008-a3 | Time Eater | 58/90 | 48 (10) | 13 | 2 | 0/8 | DOOMED |
| D-66000017-a3 | Donu and Deca | 71/110 | 34 (15) | 16 | 0 | 6/8 | WINNABLE |
| D-66000020-a3 | Time Eater | 99/99 | 43 (13) | 17 | 5 | 7/8 | WINNABLE |
| D-66000029-a2 | Collector | 82/82 | 34 (2) | 8 | 1 | 2/8 | MARGINAL |
| D-66000035-a3 | Donu and Deca | 80/80 | 44 (24) | 14 | 2 | 5/8 | WINNABLE |
| D-66000045-a3 | Awakened One | 66/82 | 38 (6) | 13 | 2 | 0/8 | DOOMED |
| D-66000047-a3 | Donu and Deca | 88/89 | 34 (11) | 16 | 3 | 5/8 | WINNABLE |
| D-66000052-a3 | Time Eater | 15/81 | 28 (10) | 15 | 0 | 0/8 | DOOMED |
| D-66000054-a2 | Champ | 80/80 | 30 (8) | 13 | 3 | 0/8 | DOOMED |
| D-66000058-a3 | Awakened One | 32/98 | 43 (27) | 14 | 3 | 0/8 | DOOMED |
| D-66000060-a3 | Time Eater | 80/80 | 45 (8) | 14 | 0 | 1/8 | MARGINAL |
| D-66000068-a3 | Time Eater | 90/90 | 46 (11) | 15 | 1 | 6/8 | WINNABLE |
| D-66000071-a1 | The Guardian | 69/85 | 18 (1) | 4 | 1 | 8/8 | WINNABLE |
| D-66000073-a3 | Time Eater | 53/83 | 38 (11) | 15 | 2 | 0/8 | DOOMED |
| D-66000082-a3 | Time Eater | 48/98 | 31 (7) | 14 | 1 | 0/8 | DOOMED |
| D-66000090-a3 | Awakened One | 56/56 | 38 (11) | 18 | 0 | 5/8 | WINNABLE |
| D-66000099-a2 | Collector | 80/80 | 28 (11) | 8 | 1 | 1/8 | MARGINAL |
| D-66000109-a2 | Champ | 59/85 | 28 (15) | 10 | 3 | 8/8 | WINNABLE |
| D-66000111-a2 | Automaton | 78/102 | 26 (6) | 12 | 3 | 8/8 | WINNABLE |
| D-66000112-a2 | Champ | 15/121 | 28 (9) | 10 | 1 | 0/8 | DOOMED |
| D-66000117-a3 | Donu and Deca | 73/86 | 36 (4) | 17 | 2 | 6/8 | WINNABLE |
| D-66000126-a2 | Champ | 85/85 | 24 (4) | 10 | 1 | 8/8 | WINNABLE |
| D-66000130-a3 | Awakened One | 84/84 | 40 (11) | 13 | 0 | 1/8 | MARGINAL |
| D-66000140-a2 | Automaton | 66/133 | 26 (7) | 8 | 3 | 8/8 | WINNABLE |
| D-66000145-a2 | Champ | 108/108 | 26 (9) | 9 | 3 | 3/8 | MARGINAL |
| D-66000146-a3 | Donu and Deca | 103/103 | 34 (7) | 17 | 1 | 3/8 | MARGINAL |
| D-66000160-a3 | Awakened One | 73/73 | 42 (20) | 14 | 0 | 0/8 | DOOMED |
| D-66000167-a2 | Champ | 22/94 | 32 (8) | 7 | 2 | 5/8 | WINNABLE |
| D-66000175-a3 | Awakened One | 44/84 | 40 (7) | 15 | 2 | 0/8 | DOOMED |
| D-66000185-a3 | Time Eater | 75/75 | 36 (8) | 18 | 2 | 0/8 | DOOMED |
| D-66000211-a2 | Collector | 77/77 | 25 (10) | 7 | 2 | 8/8 | WINNABLE |
| D-66000212-a2 | Champ | 82/116 | 24 (8) | 9 | 0 | 0/8 | DOOMED |
| D-66000226-a2 | Automaton | 80/80 | 30 (6) | 12 | 1 | 8/8 | WINNABLE |
| D-66000244-a3 | Time Eater | 22/84 | 41 (13) | 15 | 3 | 0/8 | DOOMED |

## Interpretation (separate from validity)

- About 40% of these boss deaths are fights the same combat policy usually
  wins from the same entry with another planner seed (15 entries at ≥ 4/8,
  7 at 8/8). For them the loss was planner variance, so combat consistency
  (not budget, per §377 and §387) is a lever.
- About 40% are lost on every replay, and they concentrate on the act-3 bosses
  Time Eater (7 of 10) and Awakened One (4 of 6). Doomed entries also arrive
  with less HP (61% vs 83% of max for winnable ones). **Inference:** for these
  the run is decided before the fight, either by preparation or by a
  Time Eater / Awakened One weakness of the combat policy that more search did
  not fix in §377. This experiment cannot separate those two.
- The 40% mean is conditional on a lost fight. It is not a win-rate gain: a
  re-roll would also lose some fights the policy currently wins.
- Planner repeats share one game environment; they are not independent game
  futures.

## Possible next steps (not run)

- Preparation counterfactual on the doomed Time Eater / Awakened One entries,
  for example a matched entry with a different deck or more HP, to separate
  "doomed by preparation" from "combat cannot play this boss".
- For the winnable half: whether the fights lost to planner variance share a
  pattern (early potion use, turn-1 lines), compared with the winning repeats
  of the same entry via the recorded traces in `run/*.rows.csv`.
