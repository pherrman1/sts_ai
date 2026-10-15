# §422 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Shared part = the #418 live A/B / §411 base (exact-10k live Silver, V4 OOC policy, keys off, act-3 stop).
arm_env_args() {
  local arm=$1 base=$2 run=$3
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    "STS_EXECUTABLE_GIT_SHA=$(cat "$run/GITSHA")" \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    "STS_OOC_DECISION_TRACE=$base.trace.jsonl"
  case $arm in
    off) echo STS_OOC_MCTS=0; return 0 ;;
    rollout3) ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  # §277 rollout3 profile, unchanged; the combat model is the current production CTM default (#468).
  printf '%s\n' STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native \
    STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_CPUCT=1.5 \
    STS_OOC_MCTS_WIDEN_K=2 STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 "STS_OOC_MCTS_TRACE=$base.mcts.csv"
}
