# §468 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Shared part = the §422/§433 `off` arm (exact-10k live Silver, V4 OOC policy, OOC MCTS off, keys off, act-3 stop).
#   base  legacy Silver leaf: STS_SILVER_A20_BOSS_HEAL_FIX=0 (old first-boss heal credit), all leaf opt-ins off
#   all   STS_SILVER_A20_BOSS_HEAL_FIX=1, STS_SILVER_FINAL_FIGHT_LEAF=1, STS_SILVER_NO_LOSS_POTION_CREDIT=1,
#         STS_SILVER_RELIC_HEAL_LEAF=1
R468_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R468_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines on
  case $arm in base) on=0 ;; all) on=1 ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_422 off "$base" "$run") || return 1
  [ "$(grep -cx STS_OOC_MCTS=0 <<< "$lines")" = 1 ] || { echo "§422 off env lacks STS_OOC_MCTS=0" >&2; return 1; }
  grep -q '^STS_SILVER_\(FINAL_FIGHT_LEAF\|NO_LOSS_POTION_CREDIT\|RELIC_HEAL_LEAF\|A20_BOSS_HEAL_FIX\|FINAL_BOSS_BINARY\)=' <<< "$lines" \
    && { echo "§422 env already sets a leaf option" >&2; return 1; }
  printf '%s\n' "$lines" "STS_SILVER_A20_BOSS_HEAL_FIX=$on" "STS_SILVER_FINAL_FIGHT_LEAF=$on" \
    "STS_SILVER_NO_LOSS_POTION_CREDIT=$on" "STS_SILVER_RELIC_HEAL_LEAF=$on"
}
