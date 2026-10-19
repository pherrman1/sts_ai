#!/usr/bin/env bash
# run.sh FIX SEED OUTDIR
FIX=$1 SEED=$2 O=$3
cd /home/user/sts_ai
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_BLOOD_POTION_HEAL_FIX=$FIX
  STS_FAIR=1 STS_SEARCHER3=0 STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_HEART1=/mnt/project-files/a20-winrate-check/student_sel.bin STS_OOC_MCTS=0
  STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt
  STS_CF_ALT_BOOT_FLOOR_TREES=models/candidates/v_rich_a20_419.txt
  STS_CF_ALT_BOOT_WIN_TREES=models/candidates/v_win_a20_419.txt)
t0=$(date +%s); env -i "${E[@]}" bash tools/seed_guard.sh build/linux-gcc-release/one_combat potionpriceprobe 1 "$SEED" 10000 20 "$O/f$FIX-s$SEED.csv" \
  8 1 0 all addpot:BLOOD_POTION,ooc=heart1 > "$O/f$FIX-s$SEED.log" 2>&1; rc=$?
echo "rc=$rc wall=$(( $(date +%s)-t0 ))" >> "$O/f$FIX-s$SEED.log"
