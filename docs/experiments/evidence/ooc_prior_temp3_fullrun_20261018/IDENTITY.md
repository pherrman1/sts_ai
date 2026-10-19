# Identity gate result (2026-10-18 22:18-22:24Z, author's container, before freeze)

Binary 01d0f59e… (code b5dd5557, clean build), arm C of `run_unit.sh` (temperature 1 + PIN block), vs the control
units from the winrate-check tars:

| seed | CSV row (all fields but sec) | decisions.json | mcts.csv.actions.jsonl | wall new / control |
|---|---|---|---|---|
| 111194603 | identical | byte-identical (16 lines) | byte-identical | 82 s / 179 s |
| 111194710 | identical | byte-identical (17) | byte-identical | 115 s / 226 s |
| 111194840 | identical | byte-identical (22) | byte-identical | 152 s / 319 s |
| 111194582 | identical | byte-identical (38) | byte-identical | 352 s / 703 s |

Gate PASSES: the control is reusable. (Seeds are control seeds re-run with control settings; no new seed use.)
