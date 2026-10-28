# Pre-launch smoke (seed 111387990)

Run 2026-10-26 23:30Z on one 4-CPU cloud container, each arm a separate `run_unit.sh` call with `ARMS_OVERRIDE`
(five processes at once, so walls are inflated), binary built from 4eb0b3c5 (default preset; same sources as the
v3 campaign binary 5ae5b712…). An earlier smoke (22:39Z) is void: the four parallel calls shared one output dir
and gzipped each other's files mid-run.

| arm | rc | wall s | final floor | Heart | `by=card_rule` roots |
|---|---|---|---|---|---|
| A | 0 | 501 | 40 | no | 0 |
| B | 0 | 799 | 56 (Act 4) | no | 37 |
| C | 0 | 296 | 11 | no | 7 |
| D | 0 | 3039 | 50 | no | 38 |

- **Default-off identity:** arm A on this branch vs arm A on main db216ff0 (same env, same seed): all 315 decision
  rows and 21 CTM rows identical after dropping wall/CPU fields; the only remaining difference is the path of the
  RUN dir in `policy.model_artifacts`.
- **Banners:** A has no `card_rule` and no `screens=`; B `card_rule=value` with the SR head path; C
  `card_rule=search:8192 card_rule_boss_edge=1`; D the same plus the SR head path; all keep
  `screens_a20_default=map_full_budget`.
- `card_rule` decisions occur only on card-reward screens and keep their root rows (policy capture);
  `analyze.py` ran on the four arms without error (one seed, no inference).
- **Cost:** a card search is ~60 s (8192 simulations, no stop); D spent ~2,500 s of its 3,039 s in 38 card searches.
  Expect per unit A ~500 s, B ~800 s, C and D ~3,000 s each, so ~7,300 s per unit, ~520 core-hours for 256 units,
  ~8 h wall on 16 workers x 4 lanes. C and D cost ~6x A per game.
