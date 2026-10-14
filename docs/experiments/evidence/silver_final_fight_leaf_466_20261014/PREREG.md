# §466 pre-registration: final-fight Silver leaf, fight level

Status: approved by Philipp 2026-10-14 08:57Z (decision card, 8 workers, N = 8). Coordinator assigned
§466, seeds 96000000-96999999, smokes 74068000-099.

## Question
Does Silver play the run-ending fight better when its leaf gives no value to anything left after
that fight (`STS_SILVER_FINAL_FIGHT_LEAF=1`) than with the default leaf (11 per potion on a win,
5.5 per potion on a loss)? Background: `INVESTIGATION.md` §3 (8/18 act-3 boss deaths at 10k still
held potions; wins end holding 1.0 potions).

## Frozen inputs
- Code: branch `claude/project-thread-raxk1g`, commit `8d8eeb3ceff6ad23399eabfb6d5b8ef34d987146` (pushed). Release
  `one_combat` sha256 `c92c0297…a8f5f9` (smoke build; `worker.sh` records each worker's).
- Harness: `one_combat ctmsilvergen N 0 OUT SEED teacher.json R` with
  `STS_CTMSILVER_ARMSET=finalleaf` (`worker.sh`): A0, project-fair, flat exact-10k budgets, c = 25,
  frozen OOC policy (V4 strategic stack as in §460), MCTS off. One plain-10k source run per seed;
  every act-3 boss fight is replayed (the harness filter is act 3 + boss room). In a run holding all
  three keys the act-3 boss is not run-ending, so the leaf is off in both arms there (no effect by
  construction; counted in the analysis like any other fight). The root-prior file is
  required by the harness but every arm runs with the prior off.
- Arms on each act-3 boss state: `control` (exact source replay, validity check), `base10k`
  (default leaf), `final10k` (final-fight leaf); both test arms with R replicates on the same
  per-replicate redraw of the six combat RNG streams and the same planner seed.
- Seeds: 96000000-96000255 (256 source seeds), R = 8, N = 8 workers × 4 shards × 8 seeds
  (worker W: 96000000 + 32·(W−1) .. +31), `BRIEF-worker.md`.

## Metric and analysis (`analyze.py`, frozen with this file)
- Unit: an act-3 boss fight whose control row is valid and both arms have all R replicates.
- Per fight: win rate of each arm over its R replicates; paired difference final − base.
- **Primary:** mean paired difference in win rate; 95% percentile bootstrap over source seeds,
  10,000 resamples, RNG seed 0. CI > 0 `FINAL_LEAF_HELPS`, CI < 0 `FINAL_LEAF_HURTS`, else
  `NOT_SHOWN`.
- **Secondary (descriptive):** deaths holding ≥ 1 potion per arm; potions held at win; turns;
  CPU per fight per arm; per-boss breakdown.
- **Decision:** HELPS → propose a whole-run confirmation under production Silver settings
  (learned stopping) on fresh 96M seeds; the option stays default off until that passes.
  NOT_SHOWN or HURTS → record in the ledger, no default change, stop this candidate.

## Power and cost (from the smoke, see below)
§460 had 115 act-3 boss fights per 128 seeds and a 16% control loss rate, so about 230 fights.
Per-fight paired SD of the win-rate difference ~0.2 (Inference) gives SE ≈ 1.3 pp: the run can
show an effect of about +3 pp. Cost per source seed ≈ source run + (1 + 2R) boss fights at 10k.

## Smoke (not evidence)
Seeds 74068000-003, R = 2 (`smoke-74068000.tar`): 4/4 shards rc 0, 2 seeds reached the act-3
boss (Time Eater), all rows valid, control replays matched. Boss fight at 10k ≈ 7-21 s per
replicate; source run 16-210 s per seed. `final10k` ended wins with 0 potions vs 0.33 for
`base10k`, confirming the option reaches the fight. Estimated cost for 256 seeds, R = 8:
≈ 300 s per seed ≈ 21 core-hours: about 40 min with 8 workers × 4 cores, 20 min with 16.

## Validity
Shard rc != 0 or a sha mismatch is reported, not re-run with changed settings. Excluded fights are
counted by reason. Fights finished before a shard abort count.

## Limitations
Exact 10k, not production learned stopping; A0 only (the A20 second boss is covered by the option
but not by this harness); the CTM stays trained on default-leaf play.
