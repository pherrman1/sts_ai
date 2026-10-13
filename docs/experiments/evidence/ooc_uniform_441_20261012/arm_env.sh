# §441 arm environment. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   uniform  §433 combo (4096 simulations, WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3, native leaf) with
#            STS_OOC_MCTS_PRIOR=uniform (no V4 prior in the tree) and STS_OOC_MCTS_LEAF_POLICY=uniform
#            (uniform random OOC actions inside leaf rollouts wherever V4 would decide)
#   combo    §433 combo (used only for the pairing gate in SMOKE.md)
# Both arms pin STS_OOC_PUBLIC_FUTURES=0 (= unset, the value §433 ran with), so a later default change of that
# flag on main cannot reach this run.
R441_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R441_REPO/docs/experiments/evidence/ooc_rollout3_confirm_20261011/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_433/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k
  case $arm in
    combo|uniform) ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  lines=$(arm_env_args_433 combo "$base" "$run") || return 1
  for k in STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_SIMS=4096 STS_OOC_MCTS_WIDEN_K=4 \
           STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native; do
    [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§433 combo env lacks $k" >&2; return 1; }
  done
  grep -q '^STS_OOC_PUBLIC_FUTURES=' <<< "$lines" && { echo "§433 env already sets STS_OOC_PUBLIC_FUTURES" >&2; return 1; }
  echo STS_OOC_PUBLIC_FUTURES=0
  [ "$arm" = combo ] && { printf '%s\n' "$lines"; return; }
  sed 's/^STS_OOC_MCTS_PRIOR=policy$/STS_OOC_MCTS_PRIOR=uniform/;s/^STS_OOC_MCTS_LEAF_POLICY=v4$/STS_OOC_MCTS_LEAF_POLICY=uniform/' <<< "$lines"
}
