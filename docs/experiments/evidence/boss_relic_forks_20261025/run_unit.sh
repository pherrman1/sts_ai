#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one source seed of the boss-relic fork pilot (#856). Plays the source
# game S (today's A20 default) and then, for each act-1/act-2 boss-relic root S reached, one fork per option S did
# not take (STS_OOC_FORCE_BOSS_RELIC=ACT:CHOICE, 0-2 the offered relic, 3 skip): the same seed and stack, replayed up
# to that root, the option forced, then played to the end. Always exits 0 (per-game rc in the .done lines).
# PREREG.md has the full config and provenance. Every game writes the OOC decision trace (STS_OOC_DECISION_TRACE),
# from which forks.py reads the roots and checks that each fork equals S before its root. 7 h timeout per game.
# SOURCE_ONLY=1 (smokes only) plays S and no forks.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
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
# play TAG [FORCE]: one game; FORCE is ACT:CHOICE or empty for the source.
play() {
  local tag=$1 force=${2:-} b=$OUT/$1
  [ -s "$b.done" ] && return 0
  rm -f "$b.jsonl" "$b.trace.jsonl"
  local E=("${COMMON[@]}" "STS_OOC_DECISION_TRACE=$b.trace.jsonl")
  [ -n "$force" ] && E+=("STS_OOC_FORCE_BOSS_RELIC=$force")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  local start t0 rc
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" off > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
    grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    # Today's A20 default stack: map-only OOC search at the full budget (ADR-0061), Act 4 strong (ADR-0060),
    # the M0 leaf (ADR-0057) without a value-head blend.
    grep -q "screens_a20_default=map_full_budget" "$b.log" "$b.err" || rc=94
    grep -q "Act 4 strong" "$b.log" "$b.err" || rc=93
    grep -q "leaf_calibration=-2.5384.* leaf_calibration_min_ascension=20" "$b.log" "$b.err" || rc=92
    ! grep -q "leaf_heart1_value=\| screens=" "$b.log" "$b.err" || rc=91
    if [ -n "$force" ]; then
      [ "$(grep -c '"by":"forced_boss_relic"' "$b.trace.jsonl")" = 1 ] || rc=90
      python3 -I "$REPO/docs/experiments/evidence/boss_relic_forks_20261025/forks.py" check "$OUT/S-$SEED.trace.jsonl" \
        "$b.trace.jsonl" "$force" > "$b.check" 2>&1 || rc=89
    fi
  fi
  echo "tag=$tag rc=$rc force=${force:-none} start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
}
play "S-$SEED"
# SOURCE_ONLY (smokes only): the source game alone, for a rerun-determinism check.
if [ -z "${SOURCE_ONLY:-}" ] && grep -q ' rc=0 ' "$OUT/S-$SEED.done"; then
  # One line "ACT:CHOICE" per untaken option at each act-1/act-2 boss-relic root of S.
  for f in $(python3 -I "$REPO/docs/experiments/evidence/boss_relic_forks_20261025/forks.py" plan "$OUT/S-$SEED.trace.jsonl"); do
    play "F${f/:/_}-$SEED" "$f"
  done
fi
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
