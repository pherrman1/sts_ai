#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the value-head plan's stages 1-2: one full game of the
# stage-3 control arm A (../value_level_ab_20261023/run_unit.sh COMMON, unchanged) with the leaf compare on.
# Always exits 0 (rc in the .done line). PREREG.md has the full config and provenance.
#   Leaf compare: at every searched root the same search runs once per arm on a fresh model, then 64 referee
#   rollouts (to the end of the game, plus the act-end value) from the played action and every differing pick.
#   Arms: M0, S, MS (stage-3 arms), G1B (§615), STU (§504), TD2 (§522), NULL (salted search seed). 8 h timeout (rc 124).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
for f in student_sel.bin sr_w1.bin gen1b.bin student494.bin; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
mkdir -p "$OUT"
CAL="-2.5384,-2.9227,-3.6523,-3.6334:1.0535"
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
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
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25 STS_OOC_MCTS_FAST_ROOT_CAP=1024
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
ARMS="M0@calibration=$CAL|S@heart1_value=$RUN/sr_w1.bin;heart1_weight=0.1"
ARMS+="|MS@calibration=$CAL;heart1_value=$RUN/sr_w1.bin;heart1_weight=0.1"
ARMS+="|G1B@heart1_value=$RUN/gen1b.bin|STU@student=$RUN/student494.bin"
ARMS+="|TD2@heart_model=models/candidates/heart_leaf_td2/heart_leaf.json|NULL@seed_salt=7"
b=$OUT/LC-$SEED
E+=("STS_OOC_MCTS_LEAF_COMPARE=$b.compare.jsonl" "STS_OOC_MCTS_LEAF_COMPARE_ARMS=$ARMS"
    STS_OOC_MCTS_LEAF_COMPARE_REFEREE=64 "STS_OOC_REFEREE_ACT_END=$CAL")
cd "$REPO" || exit 2
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
rm -f "$b.compare.jsonl"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 8h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
  grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
  grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
  grep -q "fast_root_cap=1024" "$b.log" "$b.err" || rc=94
  ! grep -q "leaf_calibration=\|leaf_heart1_value=" "$b.log" "$b.err" || rc=93
  grep -q "leaf_compare=$b.compare.jsonl leaf_compare_arms=M0,S,MS,G1B,STU,TD2,NULL leaf_compare_referee=64" \
    "$b.log" "$b.err" || rc=92
  grep -q "referee_act_end=-2.5384" "$b.log" "$b.err" || rc=91
  [ -s "$b.compare.jsonl" ] || rc=90
fi
echo "tag=LC-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
