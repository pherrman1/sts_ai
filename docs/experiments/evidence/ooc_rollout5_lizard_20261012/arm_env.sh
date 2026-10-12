# §446 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
#   r5liz   the §423 arm (§422 rollout3 + Lizard-capable pathb_r2_lizard CTM, explicit model and manifest) with
#           STS_OOC_MCTS_LEAF_COMBATS 3 -> 5 (the §430 change)
#   lizard  the unchanged §423 arm, used only for the launch-gate rerun
# Both pin STS_OOC_PUBLIC_FUTURES=0: #496 made 8 the default; §422/§423/§430 ran before the mixture existed.
R446_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R446_REPO/docs/experiments/evidence/ooc_rollout3_lizard_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_423/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines
  case $arm in lizard|r5liz) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_423 lizard "$base" "$run") || return 1
  [ "$(grep -cx STS_OOC_MCTS_LEAF_COMBATS=3 <<< "$lines")" = 1 ] || { echo "§423 env lacks STS_OOC_MCTS_LEAF_COMBATS=3" >&2; return 1; }
  ! grep -q '^STS_OOC_PUBLIC_FUTURES=' <<< "$lines" || { echo "§423 env already sets STS_OOC_PUBLIC_FUTURES" >&2; return 1; }
  [ "$arm" = r5liz ] && lines=$(sed 's/^STS_OOC_MCTS_LEAF_COMBATS=3$/STS_OOC_MCTS_LEAF_COMBATS=5/' <<< "$lines")
  printf '%s\n' "$lines" STS_OOC_PUBLIC_FUTURES=0
}
