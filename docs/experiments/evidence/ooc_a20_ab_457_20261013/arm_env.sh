# §457 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   off     §433 off unchanged (the §422 base: exact-10k Silver, V4 OOC gates, keys off, act-3 stop, STS_OOC_MCTS=0)
#   combo   §433 combo unchanged (4096 simulations, WIDEN_K=4, WIDEN_ALPHA=0.75, LEAF_COMBATS=3, native leaf, V4 prior
#           and leaf policy) with the automatic default CTM stack (no CTM variables set)
# Both arms pin STS_OOC_PUBLIC_FUTURES=8 (the default since #496). STS_WIN_NET stays unset (ADR-0029 default leaf
# model under OOC MCTS). Ascension 20 is the bestbench argument in run_unit.sh, not an environment variable.
R457_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R457_REPO/docs/experiments/evidence/ooc_rollout3_confirm_20261011/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_433/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines k
  case $arm in off|combo) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_433 "$arm" "$base" "$run") || return 1
  if [ "$arm" = combo ]; then
    for k in STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_SIMS=4096 \
             STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native; do
      [ "$(grep -cx "$k" <<< "$lines")" = 1 ] || { echo "§433 combo env lacks $k" >&2; return 1; }
    done
  else
    [ "$(grep -cx STS_OOC_MCTS=0 <<< "$lines")" = 1 ] || { echo "§433 off env lacks STS_OOC_MCTS=0" >&2; return 1; }
  fi
  for k in STS_OOC_PUBLIC_FUTURES STS_WIN_NET STS_OOC_MCTS_COMBAT_MODEL STS_OOC_MCTS_BREW_FALLBACK_MODEL \
           STS_OOC_MCTS_ACTIVE_LIZARD STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_OOC_MCTS_LEAF_WIN_MODEL; do
    grep -q "^$k=" <<< "$lines" && { echo "§433 env already sets $k" >&2; return 1; }
  done
  printf '%s\n' "$lines" STS_OOC_PUBLIC_FUTURES=8
}
