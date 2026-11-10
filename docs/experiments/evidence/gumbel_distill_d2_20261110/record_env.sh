# Gumbel distillation D2 (2026-11-10): §775's G16 arm (../gumbel_wholerun_20261108/run_unit.sh: net-0420 as the whole
# out-of-combat policy at temperature 0, no OOC MCTS; every fight under the whole-run Gumbel root k 16 at flat 16,000
# with max backup min 4 visits, Act 4 at Act 4 strong's budget, reuse cap and prior playouts), played by
# `one_combat silverazgen` so every searched root is recorded. Differences to §775's env, all required by silverazgen
# and inert under the whole-run Gumbel root (which never uses the learned stop): STS_SILVER_LEARNED_STOP=0 without the
# stop model, STS_SEARCHER3=0, plus the generator switches STS_AZGEN_PRODUCTION_OOC=1 (runFullRunOOC's chain),
# STS_AZGEN_PRODUCTION_COMBAT=1 (no search override) and STS_AZGEN_WHOLE_RUN_GUMBEL=1 (record the whole-run Gumbel
# root: edges[].prior, gumbelChoice, edges[].qBacked, rootQBacked). STS_OOC_HEART1 is set by run_unit.sh.
D2_ENV=(OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_MCTS=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4
  STS_AZGEN_PRODUCTION_OOC=1 STS_AZGEN_PRODUCTION_COMBAT=1 STS_AZGEN_WHOLE_RUN_GUMBEL=1)
