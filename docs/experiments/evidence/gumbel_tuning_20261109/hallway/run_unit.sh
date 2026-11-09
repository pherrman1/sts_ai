#!/usr/bin/env bash
# Gumbel tuning, hallway test (PREREG.md): one unit = one production A20 run of `one_combat selffights` on one of
# stage 2's D0 seeds, through act 3, with the control (gsh16+flat16000+mb4) and stage 2's pick c2 on copies 0-3 of
# every hallway fight and every fight in a '?' room of acts 1-3 (STS_SELF_FIGHTS_ARM_ROOMS=1M,2M,3M,1?,2?,3?).
# Production environment, main line and copy seeds exactly as ../run_unit.sh (stages 1 and 2); STS_SELF_FIGHTS_PROD=main.
# usage: run_unit.sh REPO RUN UNIT_OUT SEED hall
# Exits 0 (rc in the .done line), except exit 3 when one_combat was killed by a signal (rc 137/143, issue #1001), so
# the queue re-runs the unit as a new attempt. A timeout (rc 124) is final.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 SET=${5:-}
HERE=$REPO/docs/experiments/evidence/gumbel_tuning_20261109
[ "$SET" = hall ] || { echo "bad set '$SET' (units are SEED hall)" >&2; exit 2; }
awk -F'\t' -v s="$SEED" '$1 == s && $2 == "combine" { f = 1 } END { exit !f }' "$HERE/packages.tsv" \
  || { echo "seed $SEED is not one of stage 2's seeds" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
CTL=gsh16+flat16000+mb4
C2=gsh16+flat16000+mb4+ucb12.5+pw100+tp32+wet14.8+wch1.85
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
TAG=S-$SEED-a3-hall
b=$OUT/$TAG
E=("${COMMON[@]}" STS_SELF_FIGHTS_REPLICATES=4 STS_SELF_FIGHTS_MAX_ACT=3)
E+=("STS_SELF_FIGHTS_ARMS=$CTL,$C2" "STS_SELF_FIGHTS_ARM_ROOMS=1M,2M,3M,1?,2?,3?" STS_SELF_FIGHTS_ARM_REPLICATES=4
    STS_SELF_FIGHTS_PROD=main)
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
case $rc in 137|143) exit 3 ;; esac
exit 0
