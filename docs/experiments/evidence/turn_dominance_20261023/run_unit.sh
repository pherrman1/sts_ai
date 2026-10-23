#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT T SEED -- one guarded A20 full run (one_combat turndomgen): production Silver in
# combat (learned stop, exact root budgets, g7f_E root table + root prior 400 + tree prior K = 8, boss prior playouts),
# student_sel argmax out of combat (no OOC MCTS). Every searched Silver root gets one row of end-of-turn dominance
# (apps/one_combat/turn_dominance.cpp). Observation only. Always exits 0 (rc is in .done).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 KIND=$4 SEED=$5
[ "$KIND" = T ] || { echo "unknown unit kind $KIND" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"; base=$OUT/T-$SEED
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_DYNAMIC=FALSE OMP_NUM_THREADS=1
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1 "STS_OOC_HEART1=$RUN/student_sel.bin"
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=0)
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
env -i "${E[@]}" timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" turndomgen 1 10000 20 "$SEED" "$base.jsonl" \
  200000 40 > "$base.log" 2>&1 || rc=$?
[ $rc = 0 ] && { grep -q '"summary":true' "$base.jsonl" || rc=98; }
[ $rc = 0 ] && gzip -9 "$base.jsonl"
echo "tag=T-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
