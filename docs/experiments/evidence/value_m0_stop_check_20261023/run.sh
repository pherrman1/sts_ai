#!/usr/bin/env bash
# usage: run.sh REPO RUN OUT SEED ARM -- one profiled A20 game for the learned-OOC-stop check on M0's Q scale.
#   ARM A: the value-level A/B's arm A stack (../value_level_ab_20261023/run_unit.sh) with every searched root at the
#          full 4096 simulations: no learned OOC stop, no playout-cap randomization (no fast roots), gap stop off,
#          exact visit lock on, as in the stop's training data (§565).
#   ARM M: A plus the stage-0 calibrated leaf (M0).
# STS_RUN_PROFILE writes the root checkpoints (128..2048) that tools/ooc_learned_stop.py reads. Exits with the game's rc.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 ARM=$5
for f in student_sel.bin; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
mkdir -p "$OUT"
CAL="-2.5384,-2.9227,-3.6523,-3.6334:1.0535"
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
  
  STS_OOC_PUBLIC_FUTURES=8 
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
[ "$ARM" = A ] || [ "$ARM" = M ] || { echo "ARM must be A or M" >&2; exit 2; }
E=("${COMMON[@]}")
[ "$ARM" = M ] && E+=("STS_OOC_MCTS_LEAF_CALIBRATION=$CAL")
D=$OUT/$ARM; mkdir -p "$D"; b=$D/S-a20-$SEED
E+=("STS_RUN_PROFILE=$b.runprof.jsonl")
rm -f "$b.runprof.jsonl"
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
t0=$(date +%s)
env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -q "leaf_calibration=" "$b.log" "$b.err"; cal=$?
  { [ "$ARM" = M ] && [ "$cal" = 0 ]; } || { [ "$ARM" = A ] && [ "$cal" != 0 ]; } || rc=93
  ! grep -q "ooc-learned-stop: " "$b.log" "$b.err" || rc=97
  ! grep -q "fast_root_cap=" "$b.log" "$b.err" || rc=94
fi
echo "tag=$ARM-$SEED rc=$rc wall=$(( $(date +%s)-t0 ))" > "$b.done"
gzip -9 -f "$b.jsonl" 2>/dev/null
exit "$rc"
