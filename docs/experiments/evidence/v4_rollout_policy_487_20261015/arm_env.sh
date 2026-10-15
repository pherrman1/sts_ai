# §487 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Both arms = the §486 `v4` arm literally: §433 `combo` (the §422 base: exact-10k Silver via the bestbench budget, V4
# OOC gates at margin 1.0, keys off, act-3 stop; live OOC MCTS rollout3 at 4096 simulations, WIDEN_K=4,
# WIDEN_ALPHA=0.75, 3 leaf combats, native leaf), STS_OOC_PUBLIC_FUTURES=8, V4 tree prior (STS_OOC_MCTS_PRIOR=policy).
# No CTM variables: the automatic stack, which at ascension 20 is the calibrated pathb-a20 stack with active Lizard
# (ADR-0033). Every other setting is the binary's default on the code commit. Ascension is the bestbench argument.
# The arms differ only in the rollout (leaf) policy:
#   v4      STS_OOC_MCTS_LEAF_POLICY=v4     the ordinary policy chain (as in §486)
#   v4roll  STS_OOC_MCTS_LEAF_POLICY=prior  V4 policy-head argmax on every rollout screen V4 encodes (fixed rule
#                                           steps first), the chain elsewhere
arm_env_args() {
  local arm=$1 base=$2 run=$3 leaf
  case $arm in v4) leaf=v4 ;; v4roll) leaf=prior ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    "STS_EXECUTABLE_GIT_SHA=$(cat "$run/GITSHA")" \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    "STS_OOC_DECISION_TRACE=$base.trace.jsonl" \
    STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=4096 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native \
    STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_CPUCT=1.5 \
    STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 "STS_OOC_MCTS_TRACE=$base.mcts.csv" \
    STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_PRIOR=policy "STS_OOC_MCTS_LEAF_POLICY=$leaf"
}
