# Heart leaf A20 A/B arm environments (issue #605, §522). Sourced by run_unit.sh: arm_env_args ARM BASE RUN REPO.
# Both arms: the §504 control arm C (rollout_student_leaf_20261017/arm_env.sh) on current main with the tree prior set
# explicitly to heart1full (main's default with heart1 weights, ADR-0042): A20 Heart objective, keys collected, full
# runs, student C (`studentc.bin`) tree prior and rollout policy, rollout3 leaf (3 leaf combats), 512 sims, exact
# Silver, learned stopping off. Both arms write the root trace (HP at the Act-4 campfire; observation only).
#   C  control: the leaf end is valued by the pinned public X2-B (main's native leaf)
#   H  + STS_OOC_MCTS_LEAF_HEART_MODEL=REPO/models/candidates/heart_leaf_td2/heart_leaf.json
arm_env_args() {
  local arm=$1 base=$2 run=$3 repo=$4
  case $arm in C|H) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  [ -s "$run/studentc.bin" ] || { echo "missing $run/studentc.bin" >&2; return 1; }
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    "STS_EXECUTABLE_GIT_SHA=$(cat "$run/GITSHA")" \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0 \
    STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0 \
    STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    "STS_OOC_HEART1=$run/studentc.bin" STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=heart1full STS_OOC_MCTS_LEAF_POLICY=heart1 \
    STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_SIMS=512 \
    STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 \
    STS_OOC_PUBLIC_FUTURES=8 "STS_OOC_MCTS_TRACE=$base.mcts.csv" "STS_OOC_MCTS_ROOT_TRACE=$base.roots.jsonl"
  if [ "$arm" = H ]; then
    [ -s "$repo/models/candidates/heart_leaf_td2/heart_leaf.json" ] || { echo "missing heart leaf manifest" >&2; return 1; }
    echo "STS_OOC_MCTS_LEAF_HEART_MODEL=$repo/models/candidates/heart_leaf_td2/heart_leaf.json"
  fi
}
