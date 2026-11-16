#!/usr/bin/env bash
# Value-net leaf V2 smoke (RESULT.md): copy of ../gumbel_mb_budget_20261108/run_unit.sh (§770's environment, states and
# copy seeds). What differs: the arms (ARMS below, fixed: the Gumbel teacher g16mb = gsh16+flat16000+mb4 without and
# with the value-net leaf `lq`, and production with `lq`), their rooms (the act's boss fights only, where `lq` acts),
# STS_EXPERT_FIGHTS_MAX_ACT=<act> (the unit ends after its act; earlier fights and the main line are unchanged), the
# model input (STS_SILVER_LEAF_QNET_MODEL=$RUN/V1_d64.ctn, used only by the `lq` arms' searches; production and g16mb
# load it but never call it), its load check (rc 92) and STS_SILVER_PRIOR_MLP_FMA=0 (the prior MLP's pre-#1066
# kernel, so production and g16mb can reproduce §770 / §772). One unit = one Baalorlord run x one act [x one copy
# selection]. SEL (optional) is STS_EXPERT_FIGHTS_ARM_COPIES: the arm fights and copies this unit plays (e.g. 50:2 =
# floor 50 copy 2 only; 16 = floor 16 in full). The main line is production's either way (FightReplayer).
# usage: run_unit.sh REPO RUN UNIT_OUT RUN_ID ACT [SEL]
# 12 h timeout (rc 124); always exits 0 (rc in the .done line).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ID=$4 ACT=${5:-} SEL=${6:-}
ARMS=gsh16+flat16000+mb4,gsh16+flat16000+mb4+lq,lq
[[ -z "$SEL" || "$SEL" =~ ^[0-9]+(:[0-3])?(,[0-9]+(:[0-3])?)*$ ]] || { echo "bad selection '$SEL'" >&2; exit 2; }
[[ "$ACT" =~ ^[123]$ ]] || { echo "bad act '$ACT'" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
[ -s "$RUN/V1_d64.ctn" ] || { echo "missing $RUN/V1_d64.ctn" >&2; exit 2; }
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
  "STS_OOC_HEART1=$RUN/student_sel.bin" "STS_SILVER_LEAF_QNET_MODEL=$RUN/V1_d64.ctn" STS_SILVER_PRIOR_MLP_FMA=0)
cd "$REPO" || exit 2
TAG=F-$ID-a$ACT${SEL:+-$(printf '%s' "$SEL" | tr ':,' '-_')}
b=$OUT/$TAG
E=("${COMMON[@]}" STS_EXPERT_FIGHTS_REPLICATES=4 STS_EXPERT_FIGHTS_MAX_ACT=$ACT STS_EXPERT_FIGHTS_POTIONS=own STS_EXPERT_FIGHTS_ARMS=$ARMS STS_EXPERT_FIGHTS_ARM_ROOMS=${ACT}B STS_EXPERT_FIGHTS_ARM_REPLICATES=4)
[ -n "$SEL" ] && E+=("STS_EXPERT_FIGHTS_ARM_COPIES=$SEL")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 12h bash tools/seed_guard.sh "$RUN/one_combat" expertfights 1 "$RUN_JSON" "$b.fights.json" > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
  grep -q "learned stop gbt-0cac7cc64364" "$b.log" "$b.err" || rc=94
  grep -q '"schema":"expert-fights-v1"' "$b.fights.json" || rc=93
  grep -qF "[silver] value-net leaf model (scope 0): Q head of $RUN/V1_d64.ctn (d=64 layers=2)" "$b.log" "$b.err" || rc=92
fi
echo "tag=$TAG rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
exit 0
