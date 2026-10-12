# §433 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   off       §422 MCTS off, unchanged
#   rollout3  §422 rollout3, unchanged (2048 simulations, chance widening K=2, alpha=0.5)
#   combo     §422 rollout3 with STS_OOC_MCTS_SIMS=4096 (§427) and WIDEN_K=4, WIDEN_ALPHA=0.75 (§429)
R433_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R433_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k
  case $arm in
    off|rollout3) arm_env_args_422 "$arm" "$base" "$run"; return ;;
    combo) ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  lines=$(arm_env_args_422 rollout3 "$base" "$run") || return 1
  for k in STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_WIDEN_K=2 STS_OOC_MCTS_WIDEN_ALPHA=0.5; do
    [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§422 env lacks $k" >&2; return 1; }
  done
  sed 's/^STS_OOC_MCTS_SIMS=2048$/STS_OOC_MCTS_SIMS=4096/;s/^STS_OOC_MCTS_WIDEN_K=2$/STS_OOC_MCTS_WIDEN_K=4/;s/^STS_OOC_MCTS_WIDEN_ALPHA=0\.5$/STS_OOC_MCTS_WIDEN_ALPHA=0.75/' <<< "$lines"
}
