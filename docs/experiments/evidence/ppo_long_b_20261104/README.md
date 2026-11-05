# Long PPO run on combat B (2026-11-04)

Pre-registration: [PREREG.md](PREREG.md). Arm: [arms.txt](arms.txt). Actors: [actors_frozen.env](actors_frozen.env)
(combat B), binary and store in [screen.manifest](screen.manifest).

Launch order (author):
1. PC: `bash make_arms.sh git:https://github.com/pherrman1/sts_ai#ppo-xfer/longb heart1.bin ca8db597c04fca7d107c9e6a6517f4758c5f290496b8231690f68fad9c280ceb`
   (heart1.bin sha 1e92f2a6; check that LONG_B's net-0000 sha is 4288d095).
2. PC: `python3 tools/heart1/ppo_cloud.py serve --micro-batch 192 git:https://github.com/pherrman1/sts_ai#ppo-xfer/longb ~/ppo-longb LONG_B --keep-state 70 120 170`
   (`--keep-state` goes after the arm).
3. Workers W=1..40: `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_long_b_20261104 W`.
4. End: copy net-0070/0120/0170/0220 for the evaluation, then `ppo_cloud.py cleanup` on the PC.
