#!/usr/bin/env bash
# usage: run_bench.sh BIN ROOTS_DIR OUT_DIR GROUP BUDGET LABEL CACHE_LOG2 [ARM]
# One `one_combat rolloutpolicybench` pass (fresh Gumbel K16 + max backup 4 searches of GROUP's 13 roots at BUDGET,
# configured as a whole-run boss-room search with prior playouts; no game seed is played) under §775's G16 combat
# environment. ARM: argmax (default; production prior playout with STS_SILVER_PRIOR_PICK_CACHE=CACHE_LOG2) or
# memostat (main 6126315 with memostat.patch; CACHE_LOG2 ignored). Writes OUT_DIR/GROUP-BUDGET-pcLABEL.jsonl. Run from the repo root.
set -uo pipefail
BIN=$1 ROOTS=$2 OUT=$3 G=$4 B=$5 L=$6 PC=$7 ARM=${8:-argmax}
O=$OUT/$G-$B-pc$L
CACHE=(); [ "$ARM" = memostat ] || CACHE=("STS_SILVER_PRIOR_PICK_CACHE=$PC")   # main + memostat.patch has no cache option
env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1 \
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 \
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt \
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4 \
  "${CACHE[@]}" "$BIN" rolloutpolicybench "$O" "$B" "$ARM" 0 < "$ROOTS/$G.jsonl" > "$O.log" 2>&1
echo "rc=$?" >> "$O.log"
