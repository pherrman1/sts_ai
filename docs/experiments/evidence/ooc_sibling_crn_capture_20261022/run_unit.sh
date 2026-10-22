#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one source of the common-seed sibling recapture; always exits 0
# (rc in the .done line). PREREG.md has the full config and its provenance.
#   heartoutcomegen policy capture with student_sel as the OOC prior and rollout net: the gen-2 A/B arm A config
#   (az_gen2_ab_20261021/run_unit.sh, §621) plus sibling capture at every searched root. Each root child (depth 1, at
#   most 64) gets 32 rollout3 repeats, and repeat r of every child of a root uses the same RNG stream
#   (STS_OOC_SIBLING_COMMON_SEEDS=1, §639). The capture runs in a forked child, so play is unchanged. 7 h timeout
#   (rc 124).
# Config: OOC MCTS 4096 sims, learned OOC stop 0.99, 25% full-budget roots with fast roots capped at 1024 sims
# (STS_OOC_MCTS_FAST_ROOT_CAP), real-combat CTM rows; real combats with the learned Silver stop (ADR-0051/0054,
# STS_SILVER_LEARNED_STOP=1 + STS_SILVER_EXACT_ROOT_BUDGETS=1), g7f_E rollout root table + root/tree prior, flexible
# keys, Wing Boots counter on, engine fixes explicit.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
for f in student_sel.bin; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
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
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25 STS_OOC_MCTS_FAST_ROOT_CAP=1024
  STS_HEART_OUTCOME_CTM_ROWS=1
  STS_OOC_SIBLING_EVERY=1 STS_OOC_SIBLING_MAX_DEPTH=1 STS_OOC_SIBLING_MAX_LEAVES=64 STS_OOC_SIBLING_REPEATS=32
  STS_OOC_SIBLING_LONG=0 STS_OOC_SIBLING_COMMON_SEEDS=1)
cd "$REPO" || exit 2
b=$OUT/S-$SEED
E=("${COMMON[@]}" "STS_OOC_HEART1=$RUN/student_sel.bin" "STS_OOC_SIBLING_CAPTURE=$b.sib.jsonl")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$b.jsonl" policy > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -q "ooc-learned-stop: .*ooc_learned_stop_trees.txt" "$b.log" "$b.err" || rc=97
  grep -q "ctm-act4-survival\] model=" "$b.log" "$b.err" || rc=96
  grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
  grep -q "fast_root_cap=1024" "$b.log" "$b.err" || rc=94
  # Every capture row must carry common seeds and 32 repeats. A run with no searched root has no rows.
  if [ -s "$b.sib.jsonl" ]; then
    python3 -I -c 'import json,sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get("commonSeeds") is not True or len(r["extra"]["repeats"]) != 32: sys.exit(1)' "$b.sib.jsonl" || rc=93
  fi
fi
rows=0; [ -f "$b.sib.jsonl" ] && rows=$(wc -l < "$b.sib.jsonl")
echo "tag=S-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) sibRows=$rows" > "$b.done"
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
