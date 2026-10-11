# §427–§430 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Each arm is the §422 rollout3 arm (production pathb-r2 CTM) with exactly one setting changed:
#   s4096    STS_OOC_MCTS_SIMS 2048 -> 4096
#   wnarrow  chance widening K=2, alpha=0.5 -> K=1, alpha=0.25 (fewer sampled outcomes per chance node)
#   wbroad   chance widening K=2, alpha=0.5 -> K=4, alpha=0.75 (more sampled outcomes per chance node)
#   r5       STS_OOC_MCTS_LEAF_COMBATS 3 -> 5
# rollout3 is the unchanged §422 arm, used only for the launch-gate rerun.
R427_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R427_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines script
  case $arm in
    rollout3) script= ;;
    s4096)   script='s/^STS_OOC_MCTS_SIMS=2048$/STS_OOC_MCTS_SIMS=4096/' ;;
    wnarrow) script='s/^STS_OOC_MCTS_WIDEN_K=2$/STS_OOC_MCTS_WIDEN_K=1/;s/^STS_OOC_MCTS_WIDEN_ALPHA=0\.5$/STS_OOC_MCTS_WIDEN_ALPHA=0.25/' ;;
    wbroad)  script='s/^STS_OOC_MCTS_WIDEN_K=2$/STS_OOC_MCTS_WIDEN_K=4/;s/^STS_OOC_MCTS_WIDEN_ALPHA=0\.5$/STS_OOC_MCTS_WIDEN_ALPHA=0.75/' ;;
    r5)      script='s/^STS_OOC_MCTS_LEAF_COMBATS=3$/STS_OOC_MCTS_LEAF_COMBATS=5/' ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  lines=$(arm_env_args_422 rollout3 "$base" "$run") || return 1
  local k
  for k in STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_WIDEN_K=2 STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_LEAF_COMBATS=3; do
    [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§422 env lacks $k" >&2; return 1; }
  done
  if [ -n "$script" ]; then
    local out; out=$(sed "$script" <<< "$lines")
    [ "$(diff <(sort <<< "$lines") <(sort <<< "$out") | grep -c '^>')" -ge 1 ] || { echo "arm $arm changed nothing" >&2; return 1; }
    printf '%s\n' "$out"
  else
    printf '%s\n' "$lines"
  fi
}
