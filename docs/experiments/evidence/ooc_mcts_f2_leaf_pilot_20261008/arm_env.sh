# Sourced by launch.sh. Base: the §384 (#417) profile, unchanged: §377 live
# profile plus an explicit act-3 stop so imagined act-3 boss wins are terminal.
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 \
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
  STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0
unset STS_WIN_NET STS_OOC_MCTS_LEAF_VALUE STS_OOC_MCTS_SCREEN_LEAF_MODEL STS_OOC_MCTS_LEAF_WIN_MODEL

mcts_env() {   # §384 mcts knobs, but the native leaf (V4 continuation to the next map)
  export STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_TEMPERATURE=1 \
    STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_WIDEN_K=2 STS_OOC_MCTS_LEAF_VALUE=native
}

arm_env() {   # arm_env NAME
  case $1 in
    # Reference: §384 flat10k, OOC MCTS off.
    flat10k) export STS_OOC_MCTS=0 ;;
    # Control: OOC MCTS, native leaf valued by X2-B.
    x2b) mcts_env; export STS_OOC_MCTS_LEAF_WIN_MODEL=models/candidates/v_win_x2b_trees.txt ;;
    # Treatment: OOC MCTS, native leaf valued by F2 (E3 + #334, §396).
    f2) mcts_env; export STS_OOC_MCTS_LEAF_WIN_MODEL=models/candidates/v_win_f2_e3_trees.txt ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
