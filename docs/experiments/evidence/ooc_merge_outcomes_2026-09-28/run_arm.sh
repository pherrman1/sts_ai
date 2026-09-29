#!/bin/bash
# Frozen #384 paired arm runner. usage: run_arm.sh ARM(control|treatment) SEED_LO N_SEEDS OUT_DIR
# Must run from the repository root at the frozen commit; BIN is the frozen binary copy.
set -euo pipefail
ARM=$1; LO=$2; N=$3; OUT=$4
: "${BIN:?set BIN to the frozen one_combat copy}"
case "$ARM" in control) MERGE=0;; treatment) MERGE=1;; *) echo "bad arm" >&2; exit 2;; esac
STEM="$OUT/${ARM}_${LO}_${N}"
for f in "$STEM.csv" "$STEM.csv.meta.json" "$STEM.mcts.csv" "$STEM.log"; do
  if [ -e "$f" ] || [ -L "$f" ]; then echo "refusing to reuse $f" >&2; exit 3; fi
done
exec env -i HOME="$HOME" PATH="$PATH" OMP_NUM_THREADS=2 \
 STS_EXECUTABLE_GIT_SHA=6ed6c943397c058610855f3d29d513bdf9f37a97 \
 STS_COLLECT_KEYS=0 STS_FAIR=1 STS_NATIVE_OOC=1 \
 STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_MERGE_OUTCOMES=$MERGE \
 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1 \
 STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1 \
 STS_OOC_STRATEGIC_TOK_NN="$PWD/selfplay/models/ooc_strategic_tok_final.native" \
 STS_SEARCHER3=0 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 \
 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_SEARCH=1 STS_SILVER_VNET_LEAF_DIRECT=0 STS_STOP_AFTER_ACT=3 \
 STS_OOC_MCTS_TRACE="$STEM.mcts.csv" \
 bash tools/seed_guard.sh "$BIN" bestbench 10000 "$N" 0 "$LO" "$STEM.csv" > "$STEM.log" 2>&1
