# Stage-2 leaf pilot (campaign)

`PREREG.md` has the design. Files:

- `campaign.manifest`
- `units.txt`: 2,560 units, each line the first of eight source seeds, 111780000-111788191 and 111790000-111802287.
- `run_unit.sh`: `fightendpairgen 8 FIRST 1000 20 OUT n=4,ooc=ppo default` under net-0420 in combat B.
- `analyze.py`: the pre-registered analysis.
- `BRIEF-worker.md`: the Haiku worker brief.
- `RESULT.md`: the result (GO with the deviation-1 weights; the frozen unweighted analysis is NO-GO).
- `results/analysis.json`: `analyze.py` on the 1,938 uploaded units.
- `descriptive.py` and `results/descriptive.json`: the RESULT tables and the descriptive extras (potion types with
  CIs, source-run cost, weights by act).

Share: `/mnt/project-files/fight-end-pairs-pilot`. Workers run `bash tools/cloud/worker.sh setup|start docs/experiments/evidence/fight_end_pairs_pilot_20261107 W` at RUN_COMMIT.

Code in this PR (default off): `fightendpairgen` option `ooc=ppo` (net-0420 plays as in the PPO runner), the source row's `heartKill`, and `heart1::ppoGameCounts()`. See KB `research/fight-end-pairs.md`.

## Stop

The run stops when Philipp says so, at the latest 12 h after the first worker starts. Each worker then gets `worker.sh stop` (no new units; running units finish and upload). Analysis:

```
python3 analyze.py /mnt/project-files/fight-end-pairs-pilot/units results/analysis.json
```

## Smoke

Author container, 2026-11-07, binary `96861592…`, combat B, net-0420:

- **Policy path.** On the used seeds 111769990 and 111769991, the `fightendpairgen` source run (`ooc=ppo`) equals LONG_B's `bestbench` PPO game. 111769990 is a win on floor 56 with decisions=107, single=51, fallbacks=0 and auto_gold=31. 111769991 is a loss on floor 6 with decisions=8, single=5, fallbacks=0 and auto_gold=3. The heart1 records carry `obs.v2.*`.
- **`run_unit.sh`.** On smoke seed 111789990 (N = 1): rc 0, every check passed, 163 s wall. The source run is a loss on floor 33 with 4 forks and 28 copies, 5.4 s CPU per continuation, and a 4.5 KB `jsonl.gz`.
- **`analyze.py`.** On that tar it runs end to end (1 unit, 4 forks).
