#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one guarded potionpriceprobe source run (PREREG.md); always exits 0.
# All arms are variants of the same sampled states inside one process (common random numbers):
# base, leaf:concave=2.7, leaf:concave=1.35, hp:-12, gold:-50, maxhp:-5 and one pot:<TYPE> per held type.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
NET=$RUN/student_sel.bin
[ -s "$NET" ] || { echo "missing $NET" >&2; exit 2; }
mkdir -p "$OUT"; base=$OUT/s$SEED
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_FAIR=1 STS_SEARCHER3=0 STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g6_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  "STS_OOC_HEART1=$NET" STS_OOC_MCTS=0
  STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt
  STS_CF_ALT_BOOT_FLOOR_TREES=models/candidates/v_rich_a20_419.txt
  STS_CF_ALT_BOOT_WIN_TREES=models/candidates/v_win_a20_419.txt)
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" potionpriceprobe 1 "$SEED" 10000 20 "$base.csv" \
  12 3 12 all leaf:concave=2.7,leaf:concave=1.35,gold:-50,maxhp:-5,ooc=heart1 > "$base.log" 2>&1
rc=$?
echo "tag=s$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0   # rc is in .done; the analyzer makes the result INVALID on any rc!=0 (PREREG)
