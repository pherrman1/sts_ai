#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one AZ gen-0 seed, both arms in sequence; always exits 0
# (per-arm rc in the .done lines). PREREG.md has the full config and its provenance.
#   on   heartoutcomegen policy capture: OOC MCTS 4096 sims, student_sel prior, learned OOC stop 0.99,
#        25% full-budget roots, real-combat CTM rows. 7 h timeout (rc 124).
#   off  bestbench: student_sel alone (no OOC MCTS), same seed. 2 h timeout.
# Both arms: flat exact-10k Silver real combats (run_driver.cpp refuses Silver learned stop with OOC MCTS),
# g7f_E rollout root table + root/tree prior, flexible keys, Wing Boots counter on, engine fixes explicit.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
ON=(STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=heart1full STS_OOC_MCTS_LEAF_POLICY=heart1
  STS_OOC_MCTS_TARGET_PRIOR=1 STS_OOC_MCTS_LEAF_SELECTS=heart1 STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=500
  STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_SIMS=4096
  STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1
  STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75
  STS_OOC_MCTS_PRUNE_UNSUPPORTED=1 STS_OOC_MCTS_GAP_STOP=0
  STS_OOC_MCTS_LEARNED_STOP=models/candidates/ooc_learned_stop_trees.txt:0.99
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25 STS_HEART_OUTCOME_CTM_ROWS=1)
cd "$REPO" || exit 2
b=$OUT/on-$SEED; E=("${COMMON[@]}" "${ON[@]}"); printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
  grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
fi
echo "tag=on-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
b=$OUT/off-$SEED; E=("${COMMON[@]}" STS_OOC_CPU_PROFILE=1 "STS_OOC_DECISION_TRACE=$b.ooc.jsonl")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 20 "$SEED" "$b.csv" > "$b.log" 2> "$b.err"
rc=$?
echo "tag=off-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
