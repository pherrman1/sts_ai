#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the OOC search-architecture pilot, all three arms in
# sequence (order rotated by seed % 3); always exits 0 (per-arm rc in the .done lines). PREREG.md has the full config
# and provenance. Only STS_OOC_MCTS_SEARCH_MODE differs between the arms:
#   A   mcts           today's A20 OOC MCTS (4096 sims, learned OOC stop 0.99, 25% full-budget roots, fast cap 1024).
#   B   particle       every legal root action on the same 64 particles (common random numbers), rollout3 leaf,
#                      highest particle mean.
#   C   particle_beam  B's root stage, then a beam over policy-rank plans: width 8, top 2 ranks, 3 later decisions,
#                      leaves at the same combat horizon as B.
# All arms: the same leaf (rollout3 under student_sel ending in the SR_crn_r2_s2_ep20 value head blended at w 0.1 with
# X2-B, M0-calibrated), the same tree prior, CTM (default: §672 fine-tune + table) and real combats (learned Silver
# stop + exact root budgets, g7f_E root table + prior, boss-only prior playouts), flexible keys, Wing Boots counter on,
# engine fixes explicit. 7 h timeout per arm (rc 124). ARMS_OVERRIDE (smokes only) runs a subset.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
for f in student_sel.bin sr_crn_r2_s2_ep20.bin; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
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
  "STS_OOC_MCTS_LEAF_HEART1_VALUE=$RUN/sr_crn_r2_s2_ep20.bin" STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT=0.1
  "STS_OOC_MCTS_LEAF_CALIBRATION=$CAL"
  STS_OOC_MCTS_PARTICLES=64 STS_OOC_MCTS_BEAM=8:2:3
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
ARMS=(A B C)
declare -A MODE=([A]=mcts [B]=particle [C]=particle_beam)
cd "$REPO" || exit 2
for i in 0 1 2; do
  arm=${ARMS[$(( (i + SEED) % 3 ))]}
  [ -n "${ARMS_OVERRIDE:-}" ] && [[ " $ARMS_OVERRIDE " != *" $arm "* ]] && continue
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}" "STS_OOC_MCTS_SEARCH_MODE=${MODE[$arm]}" "STS_OOC_MCTS_SEARCH_TRACE=$b.search.jsonl")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  rm -f "$b.search.jsonl"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
    grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    grep -q "fast_root_cap=1024" "$b.log" "$b.err" || rc=94
    # The same leaf in every arm: the SR head blend and the explicit M0 calibration.
    grep -qF "leaf_heart1_value=$RUN/sr_crn_r2_s2_ep20.bin leaf_heart1_value_weight=0.100000" "$b.log" "$b.err" || rc=93
    grep -q "leaf_calibration=-2.5384" "$b.log" "$b.err" || rc=92
    # The banner must show exactly this arm's planner.
    case $arm in
      A) ! grep -q "search_mode=" "$b.log" "$b.err" || rc=91;;
      B) grep -q "search_mode=particle particles=64 horizon_combats=3" "$b.log" "$b.err" || rc=91;;
      C) grep -q "search_mode=particle_beam particles=64 beam=8:2:3 horizon_combats=3" "$b.log" "$b.err" || rc=91;;
    esac
    [ -s "$b.search.jsonl" ] || rc=90
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
