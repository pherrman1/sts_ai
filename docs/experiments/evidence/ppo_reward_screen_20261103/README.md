# PPO reward screen, screen 2 (2026-11-03)

Pre-registration: [PREREG.md](PREREG.md). Arms: [arms.txt](arms.txt). Analysis: [analyze.py](analyze.py).
Potentials: `phi_floor.json` (floor table from screen 1's games), `phi_state.json` (logistic, fit on the PC from
screen 1's BASE trajectories; added before launch). CRIT_PRE's start net is pre-trained on the PC by
`tools/heart1/ppo_critic_pretrain.py` (sha and log added before launch). Actors: screen 1's `actors_frozen.env` and
binary (`screen.manifest`).

Launch order (author):
1. PC, from `~/ppo-screen1`:
   `python3 tools/heart1/ppo_phi_fit.py logistic --table docs/experiments/evidence/ppo_reward_screen_20261103/phi_floor.json --traj ~/ppo-screen1/BASE/parts/*.jsonl.gz --holdout ~/ppo-screen1/BASE_S1/parts/*.jsonl.gz --every 4 --out .../phi_state.json`
   and `python3 tools/heart1/ppo_critic_pretrain.py --init heart1.bin --traj-dir ~/ppo-screen1/BASE/parts ~/ppo-screen1/BASE_S1/parts --passes 1 --out-bin critpre.bin --log critpre.jsonl --micro-batch 192`.
2. `bash make_arms.sh git:https://github.com/pherrman1/sts_ai#ppo-xfer/screen2 heart1.bin critpre.bin 71cfd280e121811f394ec8e6c285a1aca5368e100e2f6ae005d94442a6f922d1`
3. PC: `python3 tools/heart1/ppo_cloud.py serve --micro-batch 192 git:https://github.com/pherrman1/sts_ai#ppo-xfer/screen2 ~/ppo-screen2 $(awk '!/^#/{print $1}' arms.txt)`.
4. Workers W=1..24: `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_reward_screen_20261103 W`.
5. Iteration 30: `analyze.py RUN futility.json --futility` (one look). End: `ppo_cloud.py cleanup` on the PC.
