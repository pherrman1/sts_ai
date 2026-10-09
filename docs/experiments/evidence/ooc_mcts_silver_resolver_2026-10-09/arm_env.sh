# §410 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Shared part = the #418 live A/B / §384 live profile (exact-10k live Silver, V4 OOC policy, keys off, act 3 stop).
SILVCPU_SIMS=164     # matched-CPU OOC simulations, frozen from the calibration in PREREG.md
SILVER_COMBAT_SIMS=64             # Silver simulations per root in each imagined combat (prior on)
arm_env_args() {
  local arm=$1 base=$2 run=$3 sims
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
    prod|silv2048) sims=2048 ;;
    silvcpu) sims=$SILVCPU_SIMS ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  printf '%s\n' STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=$sims STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_TEMPERATURE=1 \
    STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_WIDEN_K=2 "STS_OOC_MCTS_TRACE=$base.mcts.csv"
  case $arm in
    silv2048|silvcpu) printf '%s\n' STS_OOC_MCTS_COMBAT_RESOLVER=silver STS_OOC_MCTS_SILVER_SIMS=$SILVER_COMBAT_SIMS \
      "STS_SILVER_ROOT_PRIOR=$run/prior-natpert.compact.txt" STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
      STS_SILVER_ROOT_PRIOR_SCOPE=override ;;
  esac
}
