# §463 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   fixon   the §459 `planner` arm: §433 combo with the public X2-B win model (ADR-0029), 8 public futures
#           (ADR-0028), STS_OOC_MCTS_ROLLOUT_SHOP=planner and STS_OOC_SHOP_DECK_SIZE_FIX=1 (ADR-0030 default)
#   fixoff  the same with STS_OOC_SHOP_DECK_SIZE_FIX=0 (legacy deck-size accounting)
R463_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R463_REPO/docs/experiments/evidence/ooc_greedy_shop_459_20261013/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_459/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines fix
  case $arm in fixon) fix=1 ;; fixoff) fix=0 ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_459 planner "$base" "$run") || return 1
  [ "$(grep -cx STS_OOC_SHOP_DECK_SIZE_FIX=1 <<< "$lines")" = 1 ] || { echo "§459 planner env lacks the fix pin" >&2; return 1; }
  sed "s/^STS_OOC_SHOP_DECK_SIZE_FIX=1\$/STS_OOC_SHOP_DECK_SIZE_FIX=$fix/" <<< "$lines"
}
