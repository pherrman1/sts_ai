# Per-type Silver potion weights A/B arm environments. Sourced by run_unit.sh:
#   arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Shared part = the §422/§433 `off` arm (exact-10k live Silver, OOC MCTS off, keys off, act-3 stop) on current
# defaults (ADR-0034, ADR-0036 escape penalty 12,35, #592 rollout zero-cost cap), with the distilled heart1
# student C (RUN/studentc.bin, weights.txt) taking every OOC decision it encodes (STS_OOC_HEART1; the V4 chain
# takes the rest), per Philipp 2026-10-17 16:31Z: "ooc should be studnet C".
#   base   flat 11 per held potion (the default; option unset)
#   level  11 for Fairy and Smoke Bomb, 7.8 (§510 non-Fairy pooled price) for every other potion
#   type   WEIGHTS_TYPE: §510 per-type prices shrunk toward 7.8; Fairy and Smoke Bomb 11
RPW_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RPW_REPO=$(cd "$RPW_DIR/../../../.." && pwd)
source "$RPW_REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
eval "$(declare -f arm_env_args | sed '1s/^arm_env_args/arm_env_args_422/')"
RPW_LEVEL="FAIRY_POTION=11,SMOKE_BOMB=11,*=7.8"
RPW_TYPE=$(cat "$RPW_DIR/WEIGHTS_TYPE")
arm_env_args() {
  local arm=$1 base=$2 run=$3 lines w
  case $arm in base) w= ;; level) w=$RPW_LEVEL ;; type) w=$RPW_TYPE ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  lines=$(arm_env_args_422 off "$base" "$run") || return 1
  [ "$(grep -cx STS_OOC_MCTS=0 <<< "$lines")" = 1 ] || { echo "§422 off env lacks STS_OOC_MCTS=0" >&2; return 1; }
  grep -q '^STS_SILVER_POTION_WEIGHTS=\|^STS_SILVER_ESCAPE_PENALTY=\|^STS_OOC_HEART1=' <<< "$lines" \
    && { echo "§422 env already sets an option this run controls" >&2; return 1; }
  [ -s "$run/studentc.bin" ] || { echo "missing $run/studentc.bin" >&2; return 1; }
  printf '%s\n' "$lines" "STS_OOC_HEART1=$run/studentc.bin"
  [ -n "$w" ] && echo "STS_SILVER_POTION_WEIGHTS=$w"
  return 0
}
