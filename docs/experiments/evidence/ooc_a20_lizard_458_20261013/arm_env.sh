# §458 arm environment. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   combo_liz  §457 `combo` unchanged (§433 combo, PUBLIC_FUTURES=8, A20 research-candidate CTM from RUN/ctm/) with the
#              §443 Step 1b Lizard candidate staged by worker.sh (ctm_artifacts.txt here) and STS_OOC_MCTS_ACTIVE_LIZARD=1.
# The only change from §457 `combo` is the CTM files and the active-Lizard switch; off and combo_def come from §457.
R458_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$R458_DIR/../ooc_a20_ab_457_20261013/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_457/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines lz
  [ "$arm" = combo_liz ] || { echo "unknown arm $arm" >&2; return 1; }
  lines=$(arm_env_args_457 combo "$base" "$run") || return 1
  [ "$(grep -c '^STS_OOC_MCTS_ACTIVE_LIZARD=' <<< "$lines")" = 1 ] || { echo "§457 combo env lacks ACTIVE_LIZARD" >&2; return 1; }
  lz=$(awk '$1=="active_lizard"{print $2}' "$R458_DIR/ctm_artifacts.txt")
  [ "$lz" = 1 ] || { echo "ctm_artifacts.txt must set active_lizard 1" >&2; return 1; }
  sed 's/^STS_OOC_MCTS_ACTIVE_LIZARD=.*/STS_OOC_MCTS_ACTIVE_LIZARD=1/' <<< "$lines"
}
