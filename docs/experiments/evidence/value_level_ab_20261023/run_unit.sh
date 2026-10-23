#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the value-level 2x2 A/B, all four arms in sequence (order
# rotated by seed % 4); always exits 0 (per-arm rc in the .done lines). PREREG.md has the full config and provenance.
#   A   the gen-2 A/B arm A config (§621): student_sel OOC prior and rollout net, rollout3 leaf ending in X2-B.
#   M   A plus the per-act calibrated leaf (M0): STS_OOC_MCTS_LEAF_CALIBRATION, fit in stage 0 (value_death_price).
#   S   A plus the SR_w1 value-head blend at w 0.1 (STS_OOC_MCTS_LEAF_HEART1_VALUE + _WEIGHT, §641/§645).
#   MS  both. Nothing else differs. 7 h timeout per arm (rc 124).
# All arms: OOC MCTS 4096 sims, learned OOC stop 0.99, 25% full-budget roots with fast roots capped at 1024 sims,
# real-combat CTM rows; real combats with the learned Silver stop (STS_SILVER_LEARNED_STOP=1 +
# STS_SILVER_EXACT_ROOT_BUDGETS=1), g7f_E rollout root table + root/tree prior, boss-only prior playouts, flexible
# keys, Wing Boots counter on, engine fixes explicit.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
for f in student_sel.bin sr_w1.bin; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
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
  STS_OOC_MCTS_LEARNED_STOP=models/candidates/ooc_learned_stop_trees.txt:0.99
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25 STS_OOC_MCTS_FAST_ROOT_CAP=1024
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
ARMS=(A M S MS)
cd "$REPO" || exit 2
for i in 0 1 2 3; do
  arm=${ARMS[$(( (i + SEED) % 4 ))]}
  E=("${COMMON[@]}")
  case $arm in M|MS) E+=("STS_OOC_MCTS_LEAF_CALIBRATION=$CAL");; esac
  case $arm in S|MS) E+=("STS_OOC_MCTS_LEAF_HEART1_VALUE=$RUN/sr_w1.bin" STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT=0.1);; esac
  b=$OUT/$arm-$SEED; printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
    grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    grep -q "fast_root_cap=1024" "$b.log" "$b.err" || rc=94
    # The banner must show exactly this arm's leaf: rc 93 for the calibration, rc 92 for the blend.
    case $arm in
      M|MS) grep -q "leaf_calibration=-2.5384" "$b.log" "$b.err" || rc=93;;
      *) ! grep -q "leaf_calibration=" "$b.log" "$b.err" || rc=93;;
    esac
    case $arm in
      S|MS) grep -qF "leaf_heart1_value=$RUN/sr_w1.bin leaf_heart1_value_weight=0.100000" "$b.log" "$b.err" || rc=92;;
      *) ! grep -q "leaf_heart1_value=" "$b.log" "$b.err" || rc=92;;
    esac
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
