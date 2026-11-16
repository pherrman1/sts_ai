cd /home/user/sts_ai
C=/tmp/claude-0/-home-user/63627303-3b8f-5e69-b8e1-e309781a0735/scratchpad/calib
E=docs/experiments/evidence/rollout_prior_gumbel_20261115/candidates
ENV="OMP_NUM_THREADS=1 STS_FAIR=1 STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1 STS_SILVER_SEARCH=1 STS_SILVER_PRIOR_PLAYOUT_ELITE=0 STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8"
ARMS=g7f_E,st=$E/rp_V.txt,st=$E/rp_X-B.txt,greedy
env $ENV build/linux-gcc-release/one_combat playoutvaluebench $C/pv_root0.jsonl 64 $ARMS < $C/val_root.part00 > $C/pv_root0.log 2>&1 &
env $ENV build/linux-gcc-release/one_combat playoutvaluebench $C/pv_root1.jsonl 64 $ARMS < $C/val_root.part01 > $C/pv_root1.log 2>&1 &
env $ENV build/linux-gcc-release/one_combat playoutvaluebench $C/pv_extra.jsonl 32 $ARMS < $C/val_extra.jsonl > $C/pv_extra.log 2>&1 &
wait
echo ALLDONE
