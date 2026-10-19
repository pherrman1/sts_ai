#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT ARM ASC SEED -- one guarded A20 full run (4 h timeout: rc 124); always exits 0.
# All arms (PREREG.md): A20 full runs with keys, student_sel.bin as the OOC policy (STS_OOC_HEART1), OOC MCTS off,
# exact-10k Silver on current main defaults. Arms differ only in Silver's victory-leaf research options:
#   base    unset (gold 0.25, max HP 2, flat 11 per potion, linear HP)
#   W       gold 0.01, max HP 1.1, potions 5.0 (Fairy and Smoke Bomb 11)       -- measured levels (§TBD prices)
#   WT      gold 0.01, max HP 1.1, per-type potion weights WEIGHTS_TYPE         -- measured per-type prices
#   K27     concave HP k=2.7 (fitted)          K135    concave HP k=1.35 (milder)
#   WTK27   WT + k=2.7                         WTK135  WT + k=1.35
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 ASC=$5 SEED=$6
D=$REPO/docs/experiments/evidence/silver_leaf_combo_20261018
LEVEL="FAIRY_POTION=11,SMOKE_BOMB=11,*=5.0"
TYPE=$(cat "$D/WEIGHTS_TYPE")
case $ARM in
  base) L=() ;;
  W) L=(STS_SILVER_GOLD_WEIGHT=0.01 STS_SILVER_MAXHP_WEIGHT=1.1 "STS_SILVER_POTION_WEIGHTS=$LEVEL") ;;
  WT) L=(STS_SILVER_GOLD_WEIGHT=0.01 STS_SILVER_MAXHP_WEIGHT=1.1 "STS_SILVER_POTION_WEIGHTS=$TYPE") ;;
  K27) L=(STS_SILVER_CONCAVE_HP_LEAF=2.7) ;;
  K135) L=(STS_SILVER_CONCAVE_HP_LEAF=1.35) ;;
  WTK27) L=(STS_SILVER_GOLD_WEIGHT=0.01 STS_SILVER_MAXHP_WEIGHT=1.1 "STS_SILVER_POTION_WEIGHTS=$TYPE" STS_SILVER_CONCAVE_HP_LEAF=2.7) ;;
  WTK135) L=(STS_SILVER_GOLD_WEIGHT=0.01 STS_SILVER_MAXHP_WEIGHT=1.1 "STS_SILVER_POTION_WEIGHTS=$TYPE" STS_SILVER_CONCAVE_HP_LEAF=1.35) ;;
  *) echo "unknown arm $ARM" >&2; exit 2 ;;
esac
NET=student_sel.bin
[ "$ASC" = 20 ] || { echo "ascension must be 20" >&2; exit 2; }
[ -s "$RUN/$NET" ] && [ -n "$TYPE" ] || { echo "missing $RUN/$NET or WEIGHTS_TYPE" >&2; exit 2; }
mkdir -p "$OUT"; base=$OUT/$ARM-a$ASC-$SEED
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  "STS_OOC_HEART1=$RUN/$NET" STS_OOC_MCTS=0 "${L[@]}")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 "$ASC" "$SEED" "$base.csv" > "$base.log" 2>&1
rc=$?
echo "tag=$ARM-a$ASC-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0   # rc is in .done; the analyzer excludes rc!=0 units (PREREG), so the tar always uploads
