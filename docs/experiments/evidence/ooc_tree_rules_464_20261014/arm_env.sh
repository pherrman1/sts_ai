# §464 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   combo      the §459 `planner` arm exactly: §433 combo with the current defaults pinned (public X2-B win model,
#              8 public futures, STS_OOC_SHOP_DECK_SIZE_FIX=1, STS_OOC_MCTS_ROLLOUT_SHOP=planner)
#   rulesmerge the same with STS_OOC_MCTS_TREE_RULES=1 and STS_OOC_MCTS_MERGE_OUTCOMES=1
# Both arms write the observation-only per-search decision log (STS_OOC_MCTS_DECISION_LOG).
R464_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R464_REPO/docs/experiments/evidence/ooc_greedy_shop_459_20261013/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_459/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k
  case $arm in combo|rulesmerge) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_459 planner "$base" "$run") || return 1
  [ "$(grep -cx STS_OOC_SHOP_DECK_SIZE_FIX=1 <<< "$lines")" = 1 ] || { echo "§459 planner env lacks the deck-size pin" >&2; return 1; }
  for k in STS_OOC_MCTS_TREE_RULES STS_OOC_MCTS_MERGE_OUTCOMES STS_OOC_MCTS_DECISION_LOG; do
    grep -q "^$k=" <<< "$lines" && { echo "§459 env already sets $k" >&2; return 1; }
  done
  printf '%s\n' "$lines" "STS_OOC_MCTS_DECISION_LOG=$base.decisions.jsonl"
  [ "$arm" = rulesmerge ] && printf '%s\n' STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_MERGE_OUTCOMES=1
  return 0
}
