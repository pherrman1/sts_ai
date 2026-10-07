#!/usr/bin/env bash
# OOC MCTS boss-rollout leaf pilot (ledger §391). One bestbench process per seed,
# WORKERS concurrent processes, one CPU each.
# Usage (from a clean checkout of the frozen commit):
#   run.sh BINARY BINARY_SHA256 EXEC_GIT_SHA OUT SEED_LO SEED_HI [WORKERS]
# BINARY is copied to a local temp dir and hash-checked (/mnt/project-files is noexec).
set -u
SRC=$1 SHA=$2 EXEC_SHA=$3 OUT=$4 LO=$5 HI=$6 WORKERS=${7:-4}
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
cd "$(git rev-parse --show-toplevel)"
TMP=$(mktemp -d); BIN=$TMP/one_combat
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "$SHA  $BIN" | sha256sum -c - || exit 1
mkdir -p "$OUT"
run_seed() {   # run_seed SEED CPU
  local stem=$OUT/$1
  for f in "$stem.csv" "$stem.log" "$stem.mcts.csv" "$stem.mcts.csv.actions.jsonl"; do
    if [ -e "$f" ] || [ -L "$f" ]; then echo "refusing to reuse $f" >&2; return 1; fi
  done
  # Base: #417 `mcts` arm (§377 live profile, exact-10k Silver, act-3 stop) with
  # the rollout3 look's X2-B win net; changed: no prior, boss-rollout leaf.
  { time taskset -c "$2" env -i HOME="$HOME" PATH="$PATH" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_EXECUTABLE_GIT_SHA="$EXEC_SHA" \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated \
    STS_SILVER_VNET_LEAF_DIRECT=0 \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_WIN_NET=models/candidates/v_win_x2b_trees.txt \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_PRIOR=uniform STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_TEMPERATURE=1 \
    STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_WIDEN_K=2 \
    STS_OOC_MCTS_LEAF_VALUE=bossrollout STS_OOC_MCTS_TRACE="$stem.mcts.csv" \
    bash tools/seed_guard.sh "$BIN" bestbench 10000 1 0 "$1" "$stem.csv" ; } > "$stem.log" 2>&1
  echo "exit $?" >> "$stem.log"
}
SEEDS=($(seq "$LO" "$HI"))
for ((k = 0; k < WORKERS; k++)); do
  ( for ((i = k; i < ${#SEEDS[@]}; i += WORKERS)); do run_seed "${SEEDS[$i]}" "$k"; done ) &
done
wait
echo "run done" > "$OUT/DONE.$LO-$HI"
