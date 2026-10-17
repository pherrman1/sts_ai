# Student-leaf A/B arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# All arms = the Arm C environment of the REPORT.md smoke, copied literally, with full runs (STS_STOP_AFTER_ACT=0,
# keys collected, Heart objective, as the §494 rollout targets were produced). Ascension is the bestbench argument.
#   C   rollout3 leaf, 512 simulations (control)
#   S   + STS_OOC_MCTS_LEAF_STUDENT=RUN/student494.bin, 512 simulations
#   S3  + STS_OOC_MCTS_LEAF_STUDENT=RUN/student494.bin, 1536 simulations (about the control's MCTS CPU)
arm_env_args() {
  local arm=$1 base=$2 run=$3 sims=512
  case $arm in C|S) ;; S3) sims=1536 ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
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
    STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 "STS_OOC_MCTS_SIMS=$sims" \
    STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 \
    STS_OOC_PUBLIC_FUTURES=8 "STS_OOC_MCTS_TRACE=$base.mcts.csv"
  if [ "$arm" != C ]; then
    [ -s "$run/student494.bin" ] || { echo "missing $run/student494.bin" >&2; return 1; }
    echo "STS_OOC_MCTS_LEAF_STUDENT=$run/student494.bin"
  fi
}
