#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the #880 victory-turn-penalty A/B, both arms in sequence
# (order rotated by seed % 2); always exits 0 (per-arm rc in the .done lines). PREREG.md has the full config.
# The arms differ only in STS_SILVER_VICTORY_TURN_PENALTY:
#   A  unset = SilverEvalWeights::victoryTurnPenalty 0.4 (main's default)
#   B  STS_SILVER_VICTORY_TURN_PENALTY=0 (won leaves do not depend on the combat turn)
# Both arms: the key-rules F stack (PREREG.md): student_sel alone out of combat (STS_OOC_MCTS_SCREENS=none), flexible
# keys, real combats with the learned Silver stop and exact root budgets, Act 4 strong (ADR-0060, unset = on), g7f_E root
# table + prior, boss-only prior playouts, default CTM, Wing Boots counter on, engine fixes explicit.
# STS_OOC_DECISION_TRACE writes one row per real combat (turns, outcome, room, pre/post state) and per OOC decision.
# 7 h timeout per arm (rc 124). ARMS_OVERRIDE (smokes only) runs a subset.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
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
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FAST_ROOT_CAP=1024
  STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25 STS_OOC_MCTS_SCREENS=none
  "STS_OOC_HEART1=$RUN/student_sel.bin")
ARMS=(A B)
declare -A EXTRA=([A]="" [B]="STS_SILVER_VICTORY_TURN_PENALTY=0")
cd "$REPO" || exit 2
for i in 0 1; do
  arm=${ARMS[$(( (i + SEED) % 2 ))]}
  [ -n "${ARMS_OVERRIDE:-}" ] && [[ " $ARMS_OVERRIDE " != *" $arm "* ]] && continue
  b=$OUT/$arm-$SEED
  rm -f "$b.trace.jsonl" "$b.trace.jsonl.gz" "$b.jsonl" "$b.jsonl.gz"
  read -r -a X <<< "${EXTRA[$arm]}"
  E=("${COMMON[@]}" "${X[@]}" "STS_OOC_DECISION_TRACE=$b.trace.jsonl")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" off > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
    grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    grep -q " screens=none" "$b.log" "$b.err" || rc=94
    grep -q "heart_key_rules sapphire=2 ruby=2 ruby_min_hp=0.600 emerald=1" "$b.log" "$b.err" || rc=93
    grep -q '"kind":"battle".*"turns":' "$b.trace.jsonl" || rc=92
    # The banner must show exactly this arm's victory turn penalty (printed only when a research leaf weight is set).
    case $arm in
      A) ! grep -q "victoryTurnPenalty=" "$b.log" "$b.err" || rc=91;;
      B) grep -q "research leaf: .* victoryTurnPenalty=0 " "$b.log" "$b.err" || rc=91;;
    esac
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
