#!/usr/bin/env bash
# Gumbel budget check (PREREG.md): copy of ../teacher_check_20261108/run_unit.sh (same binary, environment, copy
# seeds); only the unit split and the arms differ. One unit = one Baalorlord run x one act x one arm set:
#   SET g64    -> STS_EXPERT_FIGHTS_ARMS=gsh16+flat64000
#   SET g32f16 -> STS_EXPERT_FIGHTS_ARMS=flat16000,gsh16+flat32000
# with STS_EXPERT_FIGHTS_ARM_ROOMS=<ACT>E,<ACT>B, so arms (and production's 4 full copies) play only in that act's
# elite and boss fights. The main line is production's either way (FightReplayer), so the states equal stage 1's.
# usage: run_unit.sh REPO RUN UNIT_OUT RUN_ID ACT SET
# 12 h timeout (rc 124); always exits 0 (rc in the .done line).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ID=$4 ACT=${5:-} SET=${6:-}
case "$SET" in
  g64) ARMS=gsh16+flat64000 ;;
  g32f16) ARMS=flat16000,gsh16+flat32000 ;;
  *) echo "bad arm set '$SET'" >&2; exit 2 ;;
esac
[[ "$ACT" =~ ^[123]$ ]] || { echo "bad act '$ACT'" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
[[ "$ID" =~ ^[0-9]+$ ]] || { echo "bad run id $ID" >&2; exit 2; }
mkdir -p "$OUT"
tar -xf "$RUN/expert_runs.tar" -C "$OUT" "./$ID.json" || { echo "run $ID not in expert_runs.tar" >&2; exit 2; }
RUN_JSON=$OUT/$ID.json
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
  "STS_OOC_HEART1=$RUN/student_sel.bin")
cd "$REPO" || exit 2
b=$OUT/F-$ID-a$ACT-$SET
E=("${COMMON[@]}" STS_EXPERT_FIGHTS_REPLICATES=4 STS_EXPERT_FIGHTS_MAX_ACT=3 STS_EXPERT_FIGHTS_POTIONS=own STS_EXPERT_FIGHTS_ARMS=$ARMS STS_EXPERT_FIGHTS_ARM_ROOMS=${ACT}E,${ACT}B STS_EXPERT_FIGHTS_ARM_REPLICATES=4)
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 12h bash tools/seed_guard.sh "$RUN/one_combat" expertfights 1 "$RUN_JSON" "$b.fights.json" > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
  grep -q "learned stop gbt-0cac7cc64364" "$b.log" "$b.err" || rc=94
  grep -q '"schema":"expert-fights-v1"' "$b.fights.json" || rc=93
fi
echo "tag=F-$ID-a$ACT-$SET rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
exit 0
