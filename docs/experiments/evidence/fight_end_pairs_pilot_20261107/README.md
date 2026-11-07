# Stage-2 leaf pilot (campaign)

`PREREG.md` has the design. Files:

- `campaign.manifest`
- `units.txt`: 1,024 units, each line the first of eight source seeds, 111780000-111788191.
- `run_unit.sh`: `fightendpairgen 8 FIRST 1000 20 OUT n=4,ooc=ppo default` under net-0420 in combat B.
- `analyze.py`: the pre-registered analysis.
- `BRIEF-worker.md`: the Haiku worker brief.

Share: `/mnt/project-files/fight-end-pairs-pilot`. Workers run `bash tools/cloud/worker.sh setup|start docs/experiments/evidence/fight_end_pairs_pilot_20261107 W` at RUN_COMMIT.

Code in this PR (default off): `fightendpairgen` option `ooc=ppo` (net-0420 plays as in the PPO runner), the source row's `heartKill`, and `heart1::ppoGameCounts()`. See KB `research/fight-end-pairs.md`.

## Stop

The run stops 5.5 h after the first worker starts. Each worker then gets `worker.sh stop` (no new units; running units finish and upload). Analysis:

```
python3 analyze.py /mnt/project-files/fight-end-pairs-pilot/units results/analysis.json
```

## Smoke

Not yet run in the author container; results go here before launch.
