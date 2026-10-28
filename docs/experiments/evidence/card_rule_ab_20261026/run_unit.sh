#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the card-reward rule screen: arms A, B, C, D in sequence
# (order rotated by seed % 4); always exits 0 (per-arm rc in the .done lines). PREREG.md has the full config.
# The arms differ only in STS_OOC_MCTS_CARD_RULE* (card-reward screens; every other root is today's A20 default):
#   A  today's A20 default: student_sel decides card rewards (map-only search, ADR-0061).
#   B  value: argmax of the SR_crn_r2_s2_ep20 value head on each post-pick state, no rollout.
#   C  search: 8192 simulations split evenly over the root actions, rollout3 + X2-B (M0) leaf, best mean Q.
#   D  search: as C with the SR_crn_r2_s2_ep20 value head alone as the leaf anchor.
# B, C and D: boss edge on in the card searches. RUN holds student_sel.bin and sr_value.bin. 7 h timeout per arm.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
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
ARMS=(A B C D)
declare -A EXTRA=([A]=""
  [B]="STS_OOC_MCTS_CARD_RULE=value STS_OOC_MCTS_CARD_RULE_HEART1_VALUE=$RUN/sr_value.bin"
  [C]="STS_OOC_MCTS_CARD_RULE=search STS_OOC_MCTS_CARD_RULE_SIMS=8192 STS_OOC_MCTS_CARD_RULE_BOSS_EDGE=1"
  [D]="STS_OOC_MCTS_CARD_RULE=search STS_OOC_MCTS_CARD_RULE_SIMS=8192 STS_OOC_MCTS_CARD_RULE_BOSS_EDGE=1 STS_OOC_MCTS_CARD_RULE_HEART1_VALUE=$RUN/sr_value.bin")
declare -A BANNER=([A]="" [B]=" card_rule=value card_rule_heart1_value=" [C]=" card_rule=search:8192 card_rule_boss_edge=1"
  [D]=" card_rule=search:8192 card_rule_heart1_value=")
cd "$REPO" || exit 2
for i in 0 1 2 3; do
  arm=${ARMS[$(( (i + SEED) % 4 ))]}
  [ -n "${ARMS_OVERRIDE:-}" ] && [[ " $ARMS_OVERRIDE " != *" $arm "* ]] && continue
  b=$OUT/$arm-$SEED
  read -r -a X <<< "${EXTRA[$arm]}"
  E=("${COMMON[@]}" "${X[@]}")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
    grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    grep -q "fast_root_cap=1024" "$b.log" "$b.err" || rc=94
    grep -q "leaf_calibration=-2.5384.* leaf_calibration_min_ascension=20" "$b.log" "$b.err" || rc=93
    ! grep -q " screens=" "$b.log" "$b.err" || rc=92
    if [ "$arm" = A ]; then ! grep -q " card_rule=" "$b.log" "$b.err" || rc=91
    else grep -qF "${BANNER[$arm]}" "$b.log" "$b.err" || rc=91; fi
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
