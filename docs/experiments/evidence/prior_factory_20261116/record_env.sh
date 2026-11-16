# Prior data factory (issue #1053 next prior, 2026-11-16; plan: /mnt/project-files/rollout-prior-next/PLAN.md):
# D2's environment (../gumbel_distill_d2_20261110/record_env.sh: §775's G16 + mb4, net-0420 as the whole
# out-of-combat policy at temperature 0, played by `one_combat silverazgen` so every searched root is recorded) plus
# STS_AZGEN_EXTRA_LABELS: after each played whole-run Gumbel root search, up to 2 interior tree nodes (decision
# nodes with >= 256 visits, PLAYER_NORMAL, more than one edge) and up to 2 states that the search's playouts visited
# (reservoir sample over all playout steps) are each labelled by a fresh Gumbel root search at 2,000 simulations
# with the played search's configuration (g7f_E root / tree prior and playouts, k 16, max backup 4). They are
# written as rows of kind "extra". Play is bit-identical to D2's (the shadow searches use their own searcher and
# RNG; the smoke in RESULT checks it). STS_OOC_HEART1 is set by run_unit.sh.
FACTORY_ENV=(OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_MCTS=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4
  STS_AZGEN_PRODUCTION_OOC=1 STS_AZGEN_PRODUCTION_COMBAT=1 STS_AZGEN_WHOLE_RUN_GUMBEL=1
  STS_AZGEN_EXTRA_LABELS=nodes:2,playouts:2,sims:2000,minvisits:256)
