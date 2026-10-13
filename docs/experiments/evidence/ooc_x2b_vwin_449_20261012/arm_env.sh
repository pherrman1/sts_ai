# §449 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   vwin    §433 combo (4096 simulations, WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3, native leaf, V4 prior and
#           leaf policy) with STS_WIN_NET=models/v_win_trees.txt (B0, the process default, pinned explicitly)
#   x2bpub  the same with STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt (§444 public X2-B)
# Both arms pin STS_OOC_PUBLIC_FUTURES=8 (the default since #496), so a later default change cannot reach this run.
R449_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R449_REPO/docs/experiments/evidence/ooc_rollout3_confirm_20261011/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_433/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k net
  case $arm in
    vwin) net=models/v_win_trees.txt ;;
    x2bpub) net=models/candidates/v_win_x2b_public_trees.txt ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  lines=$(arm_env_args_433 combo "$base" "$run") || return 1
  for k in STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_SIMS=4096 \
           STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native; do
    [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§433 combo env lacks $k" >&2; return 1; }
  done
  for k in STS_OOC_PUBLIC_FUTURES STS_WIN_NET STS_OOC_MCTS_LEAF_WIN_MODEL; do
    grep -q "^$k=" <<< "$lines" && { echo "§433 env already sets $k" >&2; return 1; }
  done
  printf '%s\n' "$lines" STS_OOC_PUBLIC_FUTURES=8 "STS_WIN_NET=$net"
}
