#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the expert-anchored student_sel A/B, both arms in sequence
# (order rotated by seed % 2); always exits 0 (per-arm rc in the .done lines). PREREG.md has the full config and
# provenance. The arms differ only in STS_OOC_HEART1:
#   A  student_sel.bin (cf6bf7fb..., today's A20 student)
#   B  expert.bin, student_sel fine-tuned toward Baalorlord's card rewards, smith targets, shop removals and boss
#      relics (PREREG.md); same network size, so CPU per call matches.
# Both arms: today's A20 OOC default: OOC MCTS only at map roots at the full budget (ADR-0061, STS_OOC_MCTS_SCREENS
# unset, fraction set), student_sel-or-candidate decides every other screen after the rule chain; default A20 leaf
# (rollout3 + X2-B with M0), default CTM, real combats with the learned Silver stop and exact root budgets, Act-4
# strong (ADR-0060, default), g7f_E root table + prior, boss-only prior playouts, flexible keys, Wing Boots counter on,
# engine fixes explicit. 7 h timeout per arm (rc 124). ARMS_OVERRIDE (smokes only) runs a subset.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
for f in student_sel.bin expert.bin; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
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
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FAST_ROOT_CAP=1024 STS_OOC_MCTS_FULL_BUDGET_FRACTION=1
  STS_HEART_OUTCOME_CTM_ROWS=1)
ARMS=(A B)
declare -A NET=([A]=student_sel.bin [B]=expert.bin)
cd "$REPO" || exit 2
for i in 0 1; do
  arm=${ARMS[$(( (i + SEED) % 2 ))]}
  [ -n "${ARMS_OVERRIDE:-}" ] && [[ " $ARMS_OVERRIDE " != *" $arm "* ]] && continue
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}" "STS_OOC_HEART1=$RUN/${NET[$arm]}")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
    grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
    grep -qF "[heart1] loaded $RUN/${NET[$arm]} " "$b.log" "$b.err" || rc=95
    grep -q "fast_root_cap=1024" "$b.log" "$b.err" || rc=94
    # The default A20 leaf: M0 calibration on, no value-head blend.
    grep -q "leaf_calibration=-2.5384.* leaf_calibration_min_ascension=20" "$b.log" "$b.err" || rc=93
    ! grep -q "leaf_heart1_value=" "$b.log" "$b.err" || rc=92
    # Today's A20 screen default: map roots only, at the full budget.
    grep -q " screens_a20_default=map_full_budget" "$b.log" "$b.err" || rc=91
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
