# E1 of the learned price head (2026-11-07)

Fight luck against the leaf pilot's CRN pairs on the same source runs: does one fresh replay per fight give the same
HP price at the fight end as the pilot's paired continuations? Design doc (German):
https://claude.ai/artifact/PzKavVUBmYiitvHLFhg7qp. E0 (offline, §698 replays): HP price 0.109 ± 0.035 pp per HP.

- `PREREG.md`: question, setup, validity gates, analysis and decision (frozen before launch).
- `units.txt`: 512 units of 16 source seeds, the pilot's first seed block 111780000-111788191 (no new seeds).
- `run_unit.sh`: `one_combat fightendpairgen 16 FIRST 1000 20 OUT n=0,ooc=ppo,luck=1,luck_identity=1 -` in the
  pilot's environment (net-0420, combat B), with row checks.
- `campaign.manifest`: code commit, binary, workers, share (`/mnt/project-files/learned-price-head/e1`).
- `BRIEF-worker.md`: the worker brief.
- `analyze.py E1_UNITS PILOT_UNITS OUT.json`: gates, luck regression, CRN slope, ratio, decision.
- `selftest_analyze.py [SEEDS]`: synthetic check of `analyze.py` (known price; same price gives GO, a CRN price
  at half gives FAIL).
- `RESULT.md`: the run and the decision (**INCONCLUSIVE**: ratio 0.87, 90% CI [0.60, 1.31]); `e1_result.json` (the
  output of `analyze.py`), `inputs.sha256` (the tars analysed).

Generator: `apps/one_combat/fight_end_pairs.cpp` (`luck=`, `luck_identity=`, `n=0`), KB
`docs/knowledge-base/research/fight-end-pairs.md`.
