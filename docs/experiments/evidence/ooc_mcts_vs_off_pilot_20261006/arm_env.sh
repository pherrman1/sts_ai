# Sourced by launch.sh. Base: the §377 live profile (silver_learned_stop/live_env.sh),
# plus an explicit act-3 stop so imagined act-3 boss wins are terminal for OOC MCTS.
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 \
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3
unset STS_WIN_NET STS_OOC_MCTS_LEAF_VALUE STS_OOC_MCTS_SCREEN_LEAF_MODEL

arm_env() {   # arm_env NAME
  case $1 in
    # A: current best non-MCTS play, learned Silver stopping (ADR-0026).
    learned) export STS_SILVER_EXACT_ROOT_BUDGETS=0 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1 STS_OOC_MCTS=0 ;;
    # C: A with the flat exact-10k Silver that live OOC MCTS requires (run_driver.cpp guard).
    flat10k) export STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 STS_OOC_MCTS=0 ;;
    # B: C plus live OOC MCTS, §383 knobs, default leaf (screengbm, ADR-0027).
    mcts) export STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 STS_OOC_MCTS=1 \
            STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_EARLY_STOP=1 \
            STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_MAX_DEPTH=32 \
            STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_TEMPERATURE=1 \
            STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_WIDEN_K=2 ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
