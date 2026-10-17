# A20 Silver budget test arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# All arms: "plain" A20 full runs (keys, Heart objective, no OOC MCTS). Every out-of-combat decision is made by
# student C (heart1 distill) policyStep; only the key rule runs before it. No STS_OOC_STRATEGIC_* is set, so no
# V4 net is loaded. STS_OOC_DECISION_TRACE records which policy made each OOC decision.
#   F   flat exact 10k Silver (control)
#   L   learned stopping (ADR-0026 GBT, checkpoints up to 10k)
#   LP  L + gen-6 MLP prior g6_E as root prior (weight 400) and tree prior (K=8)
arm_env_args() {
  local arm=$1 base=$2 run=$3 ls=0
  case $arm in F) ;; L|LP) ls=1 ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  [ -s "$run/studentc.bin" ] || { echo "missing $run/studentc.bin" >&2; return 1; }
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    "STS_EXECUTABLE_GIT_SHA=$(cat "$run/GITSHA")" \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0 \
    STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 "STS_SILVER_LEARNED_STOP=$ls" \
    STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    "STS_OOC_HEART1=$run/studentc.bin" STS_OOC_CPU_PROFILE=1 "STS_OOC_DECISION_TRACE=$base.ooc.jsonl"
  if [ "$arm" = LP ]; then
    printf '%s\n' \
      "STS_SILVER_ROOT_PRIOR=docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt" \
      STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  fi
}
