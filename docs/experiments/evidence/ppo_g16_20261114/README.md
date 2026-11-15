# PG16H24: PPO on the Gumbel G16 combat stack, Heart 24k (2026-11-14)

Pre-registration: [PREREG.md](PREREG.md). Arm: [arms.txt](arms.txt). Actors: [actors_frozen.env](actors_frozen.env)
(§775's G16 + mb4, Heart 24k). Binary and store: [screen.manifest](screen.manifest). Smoke: [smoke/](smoke/).
Status: running since 2026-11-14 00:25 CET. Combat: G16H24 (Philipp 2026-11-14 00:16 CET).

Launch order (author):
1. PC (checkout at the run commit, `~/sts-pg16`): `bash docs/experiments/evidence/ppo_g16_20261114/make_arms.sh run
   git:https://github.com/pherrman1/sts_ai#ppo-xfer/pg16h24 ~/ppo-longb/LONG_C/net-0420.bin`
2. PC: `python3 tools/heart1/ppo_cloud.py serve --micro-batch 192 git:https://github.com/pherrman1/sts_ai#ppo-xfer/pg16h24
   ~/ppo-pg16 PG16H24 --keep-state 20 40 60 80`
3. Workers W = 1..40: `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_g16_20261114 W`
   (brief: /mnt/project-files/ppo-g16/BRIEF-worker.md).
4. End: stop at the 48 h boundary (or iteration 100), copy the final net and kept nets for the evaluation, then
   `ppo_cloud.py cleanup` of the store refs on the PC.

## Mid-run binary switch (rebin), 2026-11-14 evening

Philipp asked (2026-11-14 20:23 CET) to run the loop with the exact combat speedup of #1046 (main 950b53fc: exact
g7f_E policy-MLP kernel, identical play, about 0.72-0.76x CPU on long G16 games). The run commit moves from edf25059
(code ba705ab4, one_combat 97aec5b5) to the merge of main 950b53fc into this branch (code 950b53fc, one_combat
dae7894a..., x86-64-v3 build). The store's frozen config keeps the old sha; `ppo_cloud.py rebin` writes
`PG16H24/rebin` (old 97aec5b5 -> new dae7894a) once, so actors accept both binaries. Each actor switches at its own
iteration boundary (after publishing a part, before the next net arrives), so no part mixes binaries; every part's
metadata records its `one_combat_sha256`.

Sentinel (before the rebin): seeds 112109880-112109881 (iteration 19, part 0) with net-0018, the store's env and
STS_STOP_AFTER_ACT=1, played by both binaries: see [rebin_sentinel.txt](rebin_sentinel.txt).
