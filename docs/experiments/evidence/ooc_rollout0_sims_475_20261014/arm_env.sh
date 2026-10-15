# §475 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Both arms are built from the §464 `rulesmerge` arm exactly as §472 built them (§433 combo: 4096 simulations,
# WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3, native leaf, V4 prior and leaf policy; public X2-B win model, 8 public
# futures, deck-size fix 1, tree rules 1, outcome merging 1) with STS_OOC_MCTS_ROLLOUT_SHOP=greedy (ADR-0032):
#   rollout3  = §472 `rollout3`
#   r0s16k    = §472 `rollout0` (LEAF_COMBATS=0) with STS_OOC_MCTS_SIMS=16384 (about matched MCTS CPU)
# Both arms write the observation-only per-search decision log (STS_OOC_MCTS_DECISION_LOG).
R475_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R475_REPO/docs/experiments/evidence/ooc_tree_rules_464_20261014/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_464/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines x leaf sims
  case $arm in rollout3) leaf=3 sims=4096 ;; r0s16k) leaf=0 sims=16384 ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_464 rulesmerge "$base" "$run") || return 1
  for x in STS_OOC_MCTS_ROLLOUT_SHOP=planner STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_TREE_RULES=1 \
           STS_OOC_MCTS_MERGE_OUTCOMES=1 STS_OOC_MCTS_SIMS=4096; do
    [ "$(grep -cx "$x" <<< "$lines")" = 1 ] || { echo "§464 rulesmerge env lacks $x" >&2; return 1; }
  done
  sed "s/^STS_OOC_MCTS_ROLLOUT_SHOP=planner\$/STS_OOC_MCTS_ROLLOUT_SHOP=greedy/;s/^STS_OOC_MCTS_LEAF_COMBATS=3\$/STS_OOC_MCTS_LEAF_COMBATS=$leaf/;s/^STS_OOC_MCTS_SIMS=4096\$/STS_OOC_MCTS_SIMS=$sims/" <<< "$lines"
}
