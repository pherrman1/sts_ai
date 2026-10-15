# §459 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   planner  §433 combo (4096 simulations, WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3, native leaf, V4 prior and
#            leaf policy) with the current defaults pinned: public X2-B win model (ADR-0029), 8 public futures
#            (ADR-0028), corrected shop deck-size accounting (ADR-0030), STS_OOC_MCTS_ROLLOUT_SHOP=planner
#   greedy   the same with STS_OOC_MCTS_ROLLOUT_SHOP=greedy (#523)
R459_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R459_REPO/docs/experiments/evidence/ooc_rollout3_confirm_20261011/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_433/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k
  case $arm in planner|greedy) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_433 combo "$base" "$run") || return 1
  for k in STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_SIMS=4096 \
           STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native \
           STS_OOC_STRATEGIC_SHOP=1; do
    [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§433 combo env lacks $k" >&2; return 1; }
  done
  for k in STS_OOC_PUBLIC_FUTURES STS_WIN_NET STS_OOC_MCTS_LEAF_WIN_MODEL STS_OOC_SHOP_DECK_SIZE_FIX \
           STS_OOC_MCTS_ROLLOUT_SHOP STS_SHOP_WIN STS_OOC_SHOP_BEAM; do
    grep -q "^$k=" <<< "$lines" && { echo "§433 env already sets $k" >&2; return 1; }
  done
  printf '%s\n' "$lines" STS_OOC_PUBLIC_FUTURES=8 STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt \
    STS_OOC_SHOP_DECK_SIZE_FIX=1 "STS_OOC_MCTS_ROLLOUT_SHOP=$arm"
}
