# Rollout prior stage 2 (issue #1053, 2026-11-15): §798's environment (../cheap_rollouts_ladder_20261113/record_env.sh,
# same code f9601609 and binary 5a659bd8) with other ladder arms and students: asplayed:4000 (g7f_E prior playouts,
# control; arm index 0 as in §798, so the same search salt), st:4000 and st:16000 (students/rp_V.txt every playout
# step), ste:4000 (students/rp_X-B.txt for all 11 playout encounters). Play is bit-identical to §797 / §798.
# §798's header follows.
# Cheap rollouts stage 2 (2026-11-13): §797's environment (../budget_ladder_roots_20261112/record_env.sh) without
# STS_AZGEN_BUDGET_LADDER (§797's 1k-16k ladder of the same roots is reused) and with STS_AZGEN_ROLLOUT_LADDER: every
# searched multi-edge prior-playout root (boss rooms, Act 4) is searched again by fresh Gumbel searches, one per
# playout-policy arm (PREREG.md). Play is bit-identical to §797's runs. §797's header follows.
# Budget ladder per root (2026-11-12): D2's environment (../gumbel_distill_d2_20261110/record_env.sh) plus
# STS_AZGEN_BUDGET_LADDER (fresh Gumbel root searches of every searched root at 1k / 2k / 4k / 8k / 16k after the
# played search). D2's header follows.
# Gumbel distillation D2 (2026-11-10): §775's G16 arm (../gumbel_wholerun_20261108/run_unit.sh: net-0420 as the whole
# out-of-combat policy at temperature 0, no OOC MCTS; every fight under the whole-run Gumbel root k 16 at flat 16,000
# with max backup min 4 visits, Act 4 at Act 4 strong's budget, reuse cap and prior playouts), played by
# `one_combat silverazgen` so every searched root is recorded. The learned stop is on with §775's model, as in §775:
# the stop itself is inert under the whole-run Gumbel root, but it gates Act 4 strong (ADR-0060). Differences to
# §775's env: STS_SEARCHER3=0 (required by silverazgen, a no-op), plus the generator switches
# STS_AZGEN_PRODUCTION_OOC=1 (runFullRunOOC's chain), STS_AZGEN_PRODUCTION_COMBAT=1 (no search override) and STS_AZGEN_WHOLE_RUN_GUMBEL=1 (record the whole-run Gumbel
# root: edges[].prior, gumbelChoice, edges[].qBacked, rootQBacked). STS_OOC_HEART1 is set by run_unit.sh.
# The ste arm: candidate X-B for every playout encounter (D = this campaign dir, set by run_unit.sh).
STUDENT_ENC=$(for e in AUTOMATON AWAKENED_ONE CHAMP COLLECTOR DONU_AND_DECA HEXAGHOST SHIELD_AND_SPEAR SLIME_BOSS THE_GUARDIAN THE_HEART TIME_EATER; do printf '%s=%s,' "$e" "$D/students/rp_X-B.txt"; done)
STUDENT_ENC=${STUDENT_ENC%,}
LADDER_ENV=(OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
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
  STS_AZGEN_ROLLOUT_LADDER=asplayed:4000,st:4000,ste:4000,st:16000
  STS_AZGEN_ROLLOUT_STUDENT=$D/students/rp_V.txt
  "STS_AZGEN_ROLLOUT_STUDENT_ENC=$STUDENT_ENC")
