# §473 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Shared part = the §422/§433 `off` arm (exact-10k live Silver, V4 OOC policy, OOC MCTS off, keys off, act-3 stop),
# on the ADR-0034 defaults (optional Recall filter and canonical multi-select masks on in both arms).
#   base    escape scored as a win:       STS_SILVER_ESCAPE_PENALTY=0,0
#   escape  forfeited rewards charged:    STS_SILVER_ESCAPE_PENALTY=12,35 (normal, elite; capped at half the HP left)
R473_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R473_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
R473_PENALTY=12,35
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines pen
  case $arm in base) pen=0,0 ;; escape) pen=$R473_PENALTY ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_422 off "$base" "$run") || return 1
  [ "$(grep -cx STS_OOC_MCTS=0 <<< "$lines")" = 1 ] || { echo "§422 off env lacks STS_OOC_MCTS=0" >&2; return 1; }
  grep -q '^STS_SILVER_ESCAPE_PENALTY=\|^STS_OOC_SKIP_OPTIONAL_RECALL=\|^STS_MULTISELECT_' <<< "$lines" \
    && { echo "§422 env already sets an option this run controls" >&2; return 1; }
  printf '%s\n' "$lines" "STS_SILVER_ESCAPE_PENALTY=$pen"
}
