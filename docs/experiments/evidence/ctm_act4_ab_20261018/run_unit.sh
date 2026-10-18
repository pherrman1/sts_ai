#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT ARM ASC SEED -- one guarded A20 full run (4 h timeout: rc 124); always exits 0.
# Arms (PREREG.md): A = the standard A20 stack (student_sel.bin as STS_OOC_HEART1, STS_OOC_MCTS_TARGET_PRIOR=1,
# STS_OOC_MCTS_LEAF_SELECTS=heart1; the §524 arm B); B = A plus STS_CTM_ACT4_SURVIVAL_MODEL (§527).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 ASC=$5 SEED=$6
case $ARM in A|B) NET=student_sel.bin ;; *) echo "unknown arm $ARM" >&2; exit 2 ;; esac
ACT4=$RUN/ctm_act4_survival_trees.txt
[ "$ASC" = 20 ] || { echo "ascension must be 20" >&2; exit 2; }
[ -s "$RUN/$NET" ] && [ -s "$ACT4" ] || { echo "missing $RUN/$NET or $ACT4" >&2; exit 2; }
mkdir -p "$OUT"; base=$OUT/$ARM-a$ASC-$SEED
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  "STS_OOC_HEART1=$RUN/$NET" STS_OOC_MCTS=1 STS_OOC_MCTS_LEAF_POLICY=heart1
  STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_SIMS=512
  STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1
  STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75
  STS_OOC_MCTS_TARGET_PRIOR=1 STS_OOC_MCTS_LEAF_SELECTS=heart1
  STS_OOC_PUBLIC_FUTURES=8 "STS_OOC_MCTS_TRACE=$base.mcts.csv" "STS_OOC_MCTS_DECISION_LOG=$base.decisions.json")
[ "$ARM" = B ] && E+=("STS_CTM_ACT4_SURVIVAL_MODEL=$ACT4")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 "$ASC" "$SEED" "$base.csv" > "$base.log" 2>&1
rc=$?
echo "tag=$ARM-a$ASC-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0   # rc is in .done; the analyzer excludes rc!=0 units (PREREG), so the tar always uploads
