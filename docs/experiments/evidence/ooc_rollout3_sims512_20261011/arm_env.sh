# §424 arm environment. Sourced by run_unit.sh: arm_env_args r512 BASE RUN -> KEY=VALUE lines for env -i.
# The §422 rollout3 arm unchanged (production pathb-r2 CTM) except STS_OOC_MCTS_SIMS=512 instead of 2048.
R424_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R424_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines
  [ "$arm" = r512 ] || { echo "unknown arm $arm" >&2; return 1; }
  lines=$(arm_env_args_422 rollout3 "$base" "$run") || return 1
  [ "$(grep -cx 'STS_OOC_MCTS_SIMS=2048' <<< "$lines")" = 1 ] || { echo "§422 env lacks SIMS=2048" >&2; return 1; }
  sed 's/^STS_OOC_MCTS_SIMS=2048$/STS_OOC_MCTS_SIMS=512/' <<< "$lines"
}
