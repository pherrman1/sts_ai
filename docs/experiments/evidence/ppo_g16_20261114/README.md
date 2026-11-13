# PG16: PPO on the Gumbel G16 combat stack (2026-11-14)

Pre-registration: [PREREG.md](PREREG.md). Arm: [arms.txt](arms.txt). Actors: [actors_frozen.env](actors_frozen.env)
(§775's G16 + mb4). Binary and store: [screen.manifest](screen.manifest). Smoke: [smoke/](smoke/).
Status: prepared, not launched (combat choice after the G12H24 gate).

Launch order (author):
1. PC (checkout at the run commit, `~/sts-pg16`): `bash docs/experiments/evidence/ppo_g16_20261114/make_arms.sh run
   git:https://github.com/pherrman1/sts_ai#ppo-xfer/pg16 ~/ppo-longb/LONG_C/net-0420.bin`
2. PC: `python3 tools/heart1/ppo_cloud.py serve --micro-batch 192 git:https://github.com/pherrman1/sts_ai#ppo-xfer/pg16
   ~/ppo-pg16 PG16 --keep-state 20 40 60 80`
3. Workers W = 1..40: `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_g16_20261114 W`
   (brief: /mnt/project-files/ppo-g16/BRIEF-worker.md).
4. End: stop at the 48 h boundary (or iteration 100), copy the final net and kept nets for the evaluation, then
   `ppo_cloud.py cleanup` of the store refs on the PC.
