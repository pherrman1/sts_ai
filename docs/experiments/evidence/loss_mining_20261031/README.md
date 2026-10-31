# A20 loss mining on existing production games (2026-10-31)

Offline analysis, no new runs, no seeds. Philipp, 2026-10-31 22:34Z: "Ja starte das mal" (systematic loss analysis:
where and why A20 runs die, which deaths a different decision could plausibly have avoided). Roadmap item X5
(one-year roadmap, docs PR #925). Findings and the gap list:
[research/a20-loss-mining.md](../../../knowledge-base/research/a20-loss-mining.md).

## Data (all games already recorded; production A20 default of their date)

| set | source | games | Heart kill | config |
|---|---|---|---|---|
| A | §727 arm A, `/mnt/project-files/value-chooser-ab/units/*.tar` (`A-<seed>.jsonl.gz`, `A-<seed>.ctm.jsonl.gz`), seeds 111312000-111313535 | 1,536 | 25.1% | RUN_COMMIT 3d62ff5e, code 8f5b17d6, binary d39c2b98 ([run_unit.sh](../value_chooser_ab_20261031/run_unit.sh), arm A) |
| R1 | §720 run-1 base games (salt 0 only, no forks), `/mnt/project-files/value-clean-labels-run1/units/*.tar` (`base-<seed>.jsonl.gz`, `.ctm.jsonl.gz`), seeds 111384000-111385023 and 111387000-111387255 | 1,280 | 26.3% | code 6af96563, binary 44188a46; §712 arm-A environment ([run_unit.sh](../value_clean_labels_run1_20261029/run_unit.sh)); the 32 pilot seeds add an observer-only capture |

Both sets: A20, flexible keys (`STS_KEY_*` policy/mask), student_sel OOC prior with map-only OOC MCTS, learned-stop
Silver with g7f_E root table and prior, Act 4 strong, boss-only prior playouts, M0 leaf calibration. Neither set uses
`STS_SILVER_INCENSE_HEART_PHASE` (default off). All analyses are run on A and R1 separately and pooled; every
headline in the KB page holds in both sets (results/*.A.txt, *.R1.txt).

Per fight the CTM row (`combat_transition_row_v2`) gives encounter, room, act, floor, the pre- and post-fight HP, max
HP, potions, potion capacity, deck, relics and outcome. The game record gives every OOC state (HP, deck, upgrades,
potions, keys at `obs.fixed_observation[7:10]`, offers) and decision. Campfire actions are inferred from the next
floor's state (Recall = Ruby key bit set; rest = HP up by about 30% of max HP or to max; smith = one more upgrade).

## Reproduce

`run_all.sh WORKDIR` (≈ 6 min on one core): extracts the records from the tars, builds one pickle per set
(`extract.py`), runs every script on A, R1 and pooled, writes `results/<script>.<set>.txt`. Needs python3 with
numpy, pandas, statsmodels. Card, relic, potion and encounter names come from `include/constants/*.h` (`names.py`).

| script | what |
|---|---|
| `basic.py` | outcome census by act × room, deaths and death rate per encounter |
| `cluster.py` | deaths by stage × entry resources (HP band, potions) |
| `boss.py` | boss death by entry-HP band, potions at entry, deaths holding potions |
| `bossreg.py` | per-act logistic boss-death models, potion/HP exchange rate, counterfactual levers |
| `rest2.py`, `act3.py` | campfire action before each boss, A20 double act-3 boss, Ruby Recall timing |
| `heart.py` | Shield & Spear → Heart transfer (HP lost, potions used) |
| `potflow.py`, `iv.py` | potion use by room; potion-offer instrument (invalid, see Limits) |
| `deckfeat.py`, `bosscond.py` | deck features per boss; do card picks change with the visible act boss |
| `lowhp.py` | non-boss deaths below 50% HP: preceding campfire and fight |

## Limits

Observational. Boss-death models control for HP, max HP, potions, deck size, upgrades, curses, Strikes/Defends,
relic count and HP lost per earlier hallway/elite fight of the act, but deck strength is only partly observed, so
lever sizes are upper bounds. The potion instrument (`iv.py`, potions offered before the boss) is **invalid**:
`potions_offered` is built from valid take actions, so a potion dropping onto a full belt is never recorded (0 of
53,450 full-belt reward states show an offer), and recorded offers depend on past drinking, i.e. on deck strength.
For the same reason `potflow.py`'s "belt full at offer 0%" is an artefact; belt-full waste is not measurable here.
Both scripts stay for transparency. `common.rests`' `lift` rule never fires (Girya adds strength, not max HP), so
lifts land in "other"; no reported number depends on it. No combat logs:
in-fight play is not observable here.
