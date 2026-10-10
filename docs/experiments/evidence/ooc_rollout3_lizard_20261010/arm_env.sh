# §423 arm environment. Sourced by run_unit.sh: arm_env_args lizard BASE RUN -> KEY=VALUE lines for env -i.
# The §422 rollout3 arm unchanged, plus the Lizard-capable research candidate fast CTM
# (production pathb-r2 fast + lizardFairy + lizardBrew; production Brew fallback; active Lizard on).
R423_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$R423_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
arm_env_args() {
  local arm=$1 base=$2 run=$3
  [ "$arm" = lizard ] || { echo "unknown arm $arm" >&2; return 1; }
  arm_env_args_422 rollout3 "$base" "$run" || return 1
  local m="$R423_REPO/docs/experiments/evidence/ooc_rollout3_lizard_20261010/candidate-v3-lizard.json"
  printf '%s\n' STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native \
    STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native \
    STS_OOC_MCTS_ACTIVE_LIZARD=1 "STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$m" \
    "STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum "$m" | cut -d' ' -f1)"
}
