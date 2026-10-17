# heart1 card-select distillation capture environment. Sourced by run_unit.sh: capture_env_args MODE BASE RUN.
# The §504 control arm C (docs/experiments/evidence/rollout_student_leaf_20261017/arm_env.sh, arm C) copied
# literally: A20 Heart objective, keys collected, full runs, student C tree prior and rollout policy, 512 sims.
#   off  as arm C (parity reference)
#   cap  + STS_OOC_HEART1_CAPTURE (every 8th prior call, plus every card select a source opens), labelled by
#        heart1 (STS_OOC_HEART1_TEACHER); observation only, decisions must equal "off"
capture_env_args() {
  local mode=$1 base=$2 run=$3
  case $mode in off|cap) ;; *) echo "unknown mode $mode" >&2; return 1 ;; esac
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
    "STS_OOC_HEART1=$run/studentc.bin" STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=heart1 STS_OOC_MCTS_LEAF_POLICY=heart1 \
    STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_SIMS=512 \
    STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 \
    STS_OOC_PUBLIC_FUTURES=8 "STS_OOC_MCTS_TRACE=$base.mcts.csv"
  if [ "$mode" = cap ]; then
    [ -s "$run/heart1.bin" ] || { echo "missing $run/heart1.bin" >&2; return 1; }
    printf '%s\n' "STS_OOC_HEART1_TEACHER=$run/heart1.bin" "STS_OOC_HEART1_CAPTURE=$base.capture.jsonl" \
      STS_OOC_HEART1_CAPTURE_EVERY=8
  fi
}
