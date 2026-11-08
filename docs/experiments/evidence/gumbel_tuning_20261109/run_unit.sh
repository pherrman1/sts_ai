#!/usr/bin/env bash
# Gumbel tuning experiment (PREREG.md), one unit = one production run x one act x one arm set [x one copy selection]
# of `one_combat selffights` on a D0 seed. Production environment as ../gumbel_mb_budget_20261108/run_unit.sh (A20,
# student_sel out of combat, production Silver with the learned stop); the run ends after act ACT.
#   SET scout -> the main line through act 3 (STS_SELF_FIGHTS_MAX_ACT=3; ACT must be 3) and production as the arm
#                `prod` on copies 0-3 of every elite and boss fight; its fights tell make_units.py which acts have arm
#                fights and how long they take, and are the reference of the reproduction check.
#   SET <id>  -> STS_SELF_FIGHTS_ARMS = the tokens of the arms listed for <id> in sets_<stage>.tsv (arm ids from
#                arms.tsv; make_units.py writes them),
#                STS_SELF_FIGHTS_ARM_ROOMS=<ACT>E,<ACT>B, STS_SELF_FIGHTS_PROD=main (production plays only the
#                copies the main line needs; the control arm is the comparison).
# SEL (optional) is STS_SELF_FIGHTS_ARM_COPIES (e.g. 50:2 = floor 50 copy 2 only).
# usage: run_unit.sh REPO RUN UNIT_OUT SEED ACT SET [SEL]
# 12 h timeout (rc 124); always exits 0 (rc in the .done line).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 ACT=${5:-} SET=${6:-} SEL=${7:-}
HERE=$REPO/docs/experiments/evidence/gumbel_tuning_20261109
[[ "$SEED" =~ ^1118[0-9]{5}$ ]] || { echo "bad seed $SEED" >&2; exit 2; }
[[ "$ACT" =~ ^[123]$ ]] || { echo "bad act '$ACT'" >&2; exit 2; }
[[ -z "$SEL" || "$SEL" =~ ^[0-9]+(:[0-3])?(,[0-9]+(:[0-3])?)*$ ]] || { echo "bad selection '$SEL'" >&2; exit 2; }
[[ "$SET" =~ ^[a-z0-9]+$ ]] || { echo "bad arm set '$SET'" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
ARMS= ROOMS=${ACT}E,${ACT}B
if [ "$SET" = scout ]; then
  [ "$ACT" = 3 ] && [ -z "$SEL" ] || { echo "scout units are SEED 3 scout" >&2; exit 2; }
  ARMS=prod ROOMS=1E,1B,2E,2B,3E,3B
else
  ids=$(cat "$HERE"/sets_*.tsv 2>/dev/null | awk -F'\t' -v s="$SET" '$1 == s { print $2 }')
  [ -n "$ids" ] || { echo "arm set '$SET' not in sets_*.tsv" >&2; exit 2; }
  for id in ${ids//,/ }; do
    t=$(awk -F'\t' -v a="$id" '$1 == a { print $NF }' "$HERE/arms.tsv")
    [ -n "$t" ] || { echo "arm '$id' not in arms.tsv" >&2; exit 2; }
    ARMS=${ARMS:+$ARMS,}$t
  done
fi
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
  "STS_OOC_HEART1=$RUN/student_sel.bin")
cd "$REPO" || exit 2
TAG=S-$SEED-a$ACT-$SET${SEL:+-$(printf '%s' "$SEL" | tr ':,' '-_')}
b=$OUT/$TAG
E=("${COMMON[@]}" STS_SELF_FIGHTS_REPLICATES=4 STS_SELF_FIGHTS_MAX_ACT=$ACT)
E+=("STS_SELF_FIGHTS_ARMS=$ARMS" "STS_SELF_FIGHTS_ARM_ROOMS=$ROOMS" STS_SELF_FIGHTS_ARM_REPLICATES=4
    STS_SELF_FIGHTS_PROD=main)
[ -n "$SEL" ] && E+=("STS_SELF_FIGHTS_ARM_COPIES=$SEL")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 12h bash tools/seed_guard.sh "$RUN/one_combat" selffights 1 "$SEED" "$b.fights.json" \
  > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
  grep -q "learned stop gbt-0cac7cc64364" "$b.log" "$b.err" || rc=94
  grep -q '"schema":"self-fights-v1"' "$b.fights.json" || rc=93
fi
echo "tag=$TAG rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
exit 0
