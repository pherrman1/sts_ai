#!/usr/bin/env bash
# Root-quality campaign unit (PREREG.md). Environment = §712 arm A (card_rule_ab_20261026/run_unit.sh, verbatim).
#   probe REPO RUN OUT SEED INDEX           phase 1: grid probe at one root, exits after the probe row
#   fork  REPO RUN OUT SEED INDEX SALT KEY   phase 2: one forked game (KEY = root candidate key, or - = production)
# RUN holds one_combat, student_sel.bin (cf6bf7fb...) and sr_value.bin (28523fb5..., SR_crn_r2_s2_ep20).
set -uo pipefail
MODE=$1 REPO=$2 RUN=$3 OUT=$4 SEED=$5 INDEX=$6
[ "$(sha256sum < "$RUN/student_sel.bin" | cut -c1-16)" = cf6bf7fb7c3147dc ] || { echo "bad $RUN/student_sel.bin" >&2; exit 2; }
[ "$(sha256sum < "$RUN/sr_value.bin" | cut -c1-16)" = 28523fb5b63c1977 ] || { echo "bad $RUN/sr_value.bin" >&2; exit 2; }
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
GRID="${GRID:-x2b:0,x2b:1,x2b:3,x2b:5,sr:0,sr:1,sr:3,sr:5}" GRID_SEEDS=${GRID_SEEDS:-4} GRID_SIMS=${GRID_SIMS:-16384}
case $MODE in
  probe) b=$OUT/probe-$SEED-$INDEX
    X=("STS_OOC_ROOT_PROBE=$b.probe.jsonl" "STS_OOC_ROOT_PROBE_INDICES=$INDEX" "STS_OOC_ROOT_PROBE_GRID=$GRID"
       "STS_OOC_ROOT_PROBE_GRID_SEEDS=$GRID_SEEDS" "STS_OOC_ROOT_PROBE_GRID_SIMS=$GRID_SIMS"
       "STS_OOC_ROOT_PROBE_EXIT=${PROBE_EXIT:-1}")
    [[ ",$GRID" == *",sr:"* ]] && X+=("STS_OOC_ROOT_PROBE_GRID_SR=$RUN/sr_value.bin")
    [ "${PROBE_EXIT:-1}" = 0 ] && unset 'X[5]';;
  fork) SALT=$7 KEY=$8; tag=$(printf '%s' "$KEY" | sha256sum | cut -c1-12); b=$OUT/fork-$SEED-$INDEX-$SALT-$tag
    X=("STS_OOC_FORCE_DECISION=$INDEX:$SALT:$KEY");;
  *) echo "mode must be probe or fork" >&2; exit 2;;
esac
rm -f "$b.probe.jsonl"
E=("${COMMON[@]}" "${X[@]}")
cd "$REPO" || exit 2
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
  grep -q "leaf_calibration=-2.5384.* leaf_calibration_min_ascension=20" "$b.log" "$b.err" || rc=93
  ! grep -q " card_rule=\| screens=" "$b.log" "$b.err" || rc=92
  if [ "$MODE" = probe ]; then
    grep -q "root_probe_grid=$GRID seeds=$GRID_SEEDS sims=$GRID_SIMS" "$b.log" "$b.err" || rc=91
    [ "$(wc -l < "$b.probe.jsonl" 2>/dev/null)" = 1 ] || rc=90
  fi
fi
echo "tag=$(basename "$b") rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
gzip -9 -f "$b.jsonl" "$b.probe.jsonl" 2>/dev/null
exit $rc
