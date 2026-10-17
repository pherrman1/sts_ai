#!/usr/bin/env bash
# potionpriceprobe cloud slice: 4 lanes over seeds FIRST..LAST, one seed per process,
# no new seed starts after DEADLINE (epoch seconds). Run from the repo root of a clone
# at the frozen commit with build/linux-gcc-release/one_combat built.
#   run_slice.sh FIRST LAST DEADLINE OUTDIR
set -euo pipefail
FIRST=$1 LAST=$2 DEADLINE=$3 OUT=$4
LANES=${LANES:-4}
mkdir -p "$OUT"
BIN=build/linux-gcc-release/one_combat
export STS_EXECUTABLE_GIT_SHA=$(git rev-parse HEAD)
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
export STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
export STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
export STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
export STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3
export STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0
export STS_OOC_MCTS=0
export STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt
export STS_CF_ALT_BOOT_FLOOR_TREES=models/candidates/v_rich_a20_419.txt
export STS_CF_ALT_BOOT_WIN_TREES=models/candidates/v_win_a20_419.txt
sha256sum "$BIN" > "$OUT/binary.sha256"
env | grep '^STS_\|^OMP_' | sort > "$OUT/env.txt"
lane() {
  local seed=$((FIRST + $1))
  while [ "$seed" -le "$LAST" ] && [ "$(date +%s)" -lt "$DEADLINE" ]; do
    bash tools/seed_guard.sh "$BIN" potionpriceprobe 1 "$seed" 10000 20 "$OUT/s$seed.csv" 8 3 12 \
      > "$OUT/s$seed.log" 2>&1 && echo "$seed ok" >> "$OUT/done.txt" || echo "$seed rc=$?" >> "$OUT/done.txt"
    seed=$((seed + LANES))
  done
}
for i in $(seq 0 $((LANES - 1))); do lane "$i" & done
wait
echo "slice $FIRST..$LAST finished $(date -u +%FT%TZ)" >> "$OUT/done.txt"
