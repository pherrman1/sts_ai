# §451 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   combo   §433 combo unchanged (4096 simulations, WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3, native leaf, V4 prior
#           and leaf policy): the same-commit control
#   s8192   combo with STS_OOC_MCTS_SIMS=8192
#   wide    combo with STS_OOC_MCTS_WIDEN_K=8 (alpha stays 0.75): twice wbroad's outcome cap at every visit count;
#           ceil(8 n^0.75) >= n for all n <= 4096, so within a 4096-simulation search every chance-node visit samples a
#           fresh outcome (no particle revisits)
# All arms pin STS_OOC_PUBLIC_FUTURES=8 (the default since #496), so a later default change cannot reach this run.
R451_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R451_REPO/docs/experiments/evidence/ooc_rollout3_confirm_20261011/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_433/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k script
  case $arm in
    combo) script='' ;;
    s8192) script='s/^STS_OOC_MCTS_SIMS=4096$/STS_OOC_MCTS_SIMS=8192/' ;;
    wide) script='s/^STS_OOC_MCTS_WIDEN_K=4$/STS_OOC_MCTS_WIDEN_K=8/' ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  lines=$(arm_env_args_433 combo "$base" "$run") || return 1
  for k in STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_SIMS=4096 \
           STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native; do
    [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§433 combo env lacks $k" >&2; return 1; }
  done
  for k in STS_OOC_PUBLIC_FUTURES STS_WIN_NET STS_OOC_MCTS_LEAF_WIN_MODEL STS_OOC_MCTS_MERGE_OUTCOMES; do
    grep -q "^$k=" <<< "$lines" && { echo "§433 env already sets $k" >&2; return 1; }
  done
  [ -n "$script" ] && lines=$(sed "$script" <<< "$lines")
  printf '%s\n' "$lines" STS_OOC_PUBLIC_FUTURES=8
}
