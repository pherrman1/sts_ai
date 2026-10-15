# §472 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   rollout3  the §464 `rulesmerge` arm (§433 combo: 4096 simulations, WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3,
#             native leaf, V4 prior and leaf policy; public X2-B win model, 8 public futures, deck-size fix 1,
#             tree rules 1, outcome merging 1) with STS_OOC_MCTS_ROLLOUT_SHOP=greedy; the ADR-0028 to ADR-0032
#             defaults are pinned explicitly
#   rollout0  the same with STS_OOC_MCTS_LEAF_COMBATS=0 (the leaf is valued at the next map screen, no extra combats)
# Both arms write the observation-only per-search decision log (STS_OOC_MCTS_DECISION_LOG).
R472_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R472_REPO/docs/experiments/evidence/ooc_tree_rules_464_20261014/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_464/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k
  case $arm in rollout3) k=3 ;; rollout0) k=0 ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_464 rulesmerge "$base" "$run") || return 1
  for x in STS_OOC_MCTS_ROLLOUT_SHOP=planner STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_TREE_RULES=1 \
           STS_OOC_MCTS_MERGE_OUTCOMES=1 STS_OOC_MCTS_SIMS=4096; do
    [ "$(grep -cx "$x" <<< "$lines")" = 1 ] || { echo "§464 rulesmerge env lacks $x" >&2; return 1; }
  done
  sed "s/^STS_OOC_MCTS_ROLLOUT_SHOP=planner\$/STS_OOC_MCTS_ROLLOUT_SHOP=greedy/;s/^STS_OOC_MCTS_LEAF_COMBATS=3\$/STS_OOC_MCTS_LEAF_COMBATS=$k/" <<< "$lines"
}
