#!/usr/bin/env bash
# Prior-share non-inferiority (README.md): one unit = arm C on one seed of §727 (value_chooser_ab_20261031). Arm C is
# §741's arm B environment verbatim (run_unit.sh of map_sims_sprt_20261101) without the explicit
# STS_OOC_MCTS_FULL_ROOT_SIMS=1024 (the A20 default since ADR-0065) plus STS_OOC_MCTS_PRIOR_SHARE_STOP=0.9 (#942).
# The 1,024 control is not re-played: §741 B records, else §727 A records (README.md, "Control reuse").
#   run_unit.sh REPO RUN OUT SEED KIND        KIND: div | sent
# RUN holds one_combat and student_sel.bin (cf6bf7fb...).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 KIND=${5:-}
case "$KIND" in div|sent) ;; *) echo "bad KIND $KIND" >&2; exit 2;; esac
HERE=$(cd "$(dirname "$0")" && pwd)
[ "$(sha256sum < "$RUN/student_sel.bin" | cut -c1-16)" = cf6bf7fb7c3147dc ] || { echo "bad $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=heart1full STS_OOC_MCTS_LEAF_POLICY=heart1
  STS_OOC_MCTS_TARGET_PRIOR=1 STS_OOC_MCTS_LEAF_SELECTS=heart1 STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=500
  STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_SIMS=4096
  STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1
  STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75
  STS_OOC_MCTS_PRUNE_UNSUPPORTED=1 STS_OOC_MCTS_GAP_STOP=0
  STS_OOC_MCTS_LEARNED_STOP=models/candidates/ooc_learned_stop_trees.txt:0.99
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FAST_ROOT_CAP=1024 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
# game TAG EXTRA...: one heartoutcomegen game with the common environment plus EXTRA; rc 0 only if it ran as frozen.
game() {
  local tag=$1; shift
  local b=$OUT/$tag E=("${COMMON[@]}" "$@") rc
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    grep -q "leaf_calibration=-2.5384.* leaf_calibration_min_ascension=20" "$b.log" "$b.err" || rc=93
    ! grep -q " card_rule=" "$b.log" "$b.err" || rc=92
  fi
  echo "$tag rc=$rc wall=$(( $(date +%s)-t0 ))" >> "$OUT/games.txt"
  return $rc
}
finish() { echo "tag=$SEED rc=$1 start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/$SEED.done"; gzip -9 -f "$OUT"/*.jsonl 2>/dev/null; exit $1; }
game "C-$SEED" STS_OOC_MCTS_PRIOR_SHARE_STOP=0.9 || finish $?
grep -q "prior_share_stop=0.900000 .*map_root_sims_a20_default=1024" "$OUT/C-$SEED.log" "$OUT/C-$SEED.err" || finish 89
! grep -q "full_root_sims=" "$OUT/C-$SEED.log" "$OUT/C-$SEED.err" || finish 88
echo "$KIND" > "$OUT/kind.txt"
finish 0
