# D2: Gumbel-16k + max-backup teacher data for the combat net (Gumbel distillation, 2026-11-10)

Data generation only: no gameplay comparison, no default change. Plan: [Gumbel-16k als Lehrer
destillieren](https://claude.ai/artifact/K2pXZEopgkhDfYofobTSZ9); follows T0
(`../gumbel_distill_t0_20261110/PREREG.md`). Philipp asked on 2026-11-10 21:35 CET for workers that collect enough
data for per-boss specialists and gave the go at 21:49 CET ("Let's go") on the proposal of 4,096 runs on 40 workers
(~650-750 lane-h).

## What

- `one_combat silverazgen` with `record_env.sh`: §775's G16 arm (net-0420 out of combat at temperature 0, no OOC
  MCTS; every fight under the whole-run Gumbel root k 16 at flat 16,000 with max backup min 4 visits; Act 4 at Act 4
  strong's budget, reuse cap 262,144 at the Heart and prior playouts). `STS_AZGEN_WHOLE_RUN_GUMBEL=1` (code 823bbad0)
  installs no search override, so the fights are bestbench's; root rows add `edges[].prior`, `gumbelChoice`,
  `edges[].qBacked` (max-backed value) and `rootQBacked`. `q` stays the mean playout value.
- 4,096 natural A20 runs on seeds 111950000-111954095, 512 units of 8 runs (`units.txt`), queue schedule, 4 lanes per
  worker; smokes 111959990-111959999. `run_unit.sh` refuses seeds outside these blocks (rc 98) and checks the
  manifest (production OOC chain, production combat with boss prior playouts, whole-run Gumbel root, max backup 4) and
  that net-0420 loaded (rc 97 / 96).
- Expected per D1 rates (Inference): ~2.3M roots, ~97k fights; per boss ~42k roots (rarest) to ~95k (Heart).

## Equivalence smoke

§775's G16 games replayed with silverazgen must match §782's per-fight table (`../gumbel_wholerun_trace_20261109/
results/battles.csv.gz`, arm G16: encounter, floor, won, turns, HP before; HP after differs by Burning Blood's +6,
which the table records after the heal) and §775's `whole-run Gumbel roots= sims=` exit line:
- Code 439d5933 (binary e7e07f02), learned stop off: 111379018 and 111378289 identical; the Heart seed 111378261
  identical through fight 30, then diverged at Shield and Spear (prelaunch review F1): the learned stop gates Act 4
  strong (ADR-0060), so Act 4 ran at flat 16k with the 32k cap (946 roots / 14.0M sims against §775's 980 / 15.87M).
- Code 823bbad0 (binary ed373563): silverazgen accepts the learned stop (with §775's model) under
  `STS_AZGEN_WHOLE_RUN_GUMBEL=1`, where the stop itself is inert, so the env equals §775's except STS_SEARCHER3=0 and
  the generator switches. The manifest records `act4Strong`; run_unit.sh requires it and the binary's Act 4 strong
  banner (rc 97). 111379018: identical (53 roots / 607,997 sims). 111378261 (Heart kill): all 32 fights identical
  to §782 (encounter, floor, won, turns, HP before) and the exit line equals §775 (roots=980 sims=15,871,840).

## Processing (after the run)

1. `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/gumbel_distill_d2_20261110 --extract <dir>`;
   units with rc != 0 are excluded and tallied.
2. `pack_states.py` (passes `qBacked`, `rootQBacked` through), then `tensorize.py` and training as in T0.
