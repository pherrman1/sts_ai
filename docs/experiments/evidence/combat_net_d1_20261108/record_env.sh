# Combat-plan stage 0 (2026-11-08): unchanged copy of ../silver_leaf_a20_prod_20261022/record_env.sh.
# The silver-leaf-a20 settings (../silver_leaf_a20_data_20261022/record_env.sh: A20, student_sel argmax out of combat
# through runFullRunOOC's chain, no OOC MCTS, flat exact budgets without the learned stop) plus
# STS_AZGEN_PRODUCTION_COMBAT=1: no self-play search override, so every fight plays the whole-run production Silver
# (g7f_E root prior with its bonus, tree prior K = 8, boss prior playouts), as bestbench does with these settings.
# STS_OOC_HEART1 is set by run_unit.sh to the frozen copy of student_sel.bin.
SL_ENV=(OMP_DYNAMIC=FALSE OMP_NUM_THREADS=1
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=0 STS_AZGEN_PRODUCTION_OOC=1 STS_AZGEN_PRODUCTION_COMBAT=1
  STS_AZGEN_GUMBEL_ROOT=16)
