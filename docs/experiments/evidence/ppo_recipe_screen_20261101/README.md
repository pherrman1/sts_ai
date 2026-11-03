# PPO recipe screen (2026-11-01)

Pre-registration: [PREREG.md](PREREG.md). Arms: [arms.txt](arms.txt). Actor env before the combat choice:
[actors_base.env](actors_base.env); `make_arms.sh` writes the frozen one (`actors_frozen.env`) and the arms into the store.

Launch order (author):
1. `bash make_arms.sh git:https://github.com/pherrman1/sts_ai#ppo-xfer/screen1 START.bin BINARY_SHA COMBAT`
   (START and COMBAT from `ppo_cost_arms_g0_20261101`), then commit `actors_frozen.env` and the binary sha in
   `screen.manifest` (the run commit).
2. PC: `python3 tools/heart1/ppo_cloud.py serve git:https://github.com/pherrman1/sts_ai#ppo-xfer/screen1 ~/ppo-screen1 $(awk '!/^#/{print $1}' arms.txt)`
   in the background (RC session).
3. Workers W=1..40: `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_recipe_screen_20261101 W`;
   after a container reset, `setup` and `start` again.
4. End (PC, deletes are refused from the cloud): `python3 tools/heart1/ppo_cloud.py cleanup git:https://github.com/pherrman1/sts_ai#ppo-xfer/screen1 $(awk '!/^#/{print $1}' arms.txt)`;
   the smoke arm likewise with `#ppo-xfer/smoke1 SMOKE`.

Result: [RESULT.md](RESULT.md) (no arm PROMISING; LAM_1 WORSE; S1 recipe = BASE). Data `s1res.tgz` (games CSVs,
loop stats, stalls, serve log), analysis `analyze.py` → `result.json`.
