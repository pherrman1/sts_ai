#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the Silver leaf price gate (PREREG.md).
# The stage-2 leaf pilot's setting (../fight_end_pairs_pilot_20261107/run_unit.sh): LONG_C's net-0420 as the whole
# out-of-combat policy (temperature 0, no OOC MCTS), combat B (flat Silver 1,000, learned stop off, Act-4 strong off,
# g7f_E root and tree prior), `one_combat bestbench 1000 1 20 SEED`, with three arms on every seed:
#   D  = the defaults (potions 11, Fairy 11 + death save, max HP 2.0, gold 0.25),
#   P1 = the stage-4 global prices: other potions 3.7, Fairy 47.6 + death save, max HP 2.4, gold 0.12,
#   PF = P1 with every non-Fairy potion at 11.
# Order rotated by seed. Exits 0; each game's ARM-SEED.done holds its rc.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = c201818cb248cef2 ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
if ! { [ "$SEED" -ge 111820000 ] && [ "$SEED" -le 111822047 ]; } && ! { [ "$SEED" -ge 111829990 ] && [ "$SEED" -le 111829999 ]; }; then
  echo "seed $SEED outside the frozen block" >&2; exit 2
fi
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_MCTS=0 STS_SILVER_ACT4_STRONG=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  "STS_OOC_HEART1=$RUN/net-0420.bin")
ARMS=(D P1 PF)
BANNER="[silver] research leaf: gold=0.12 maxhp=2.4 victoryTurnPenalty=0.4 concave=0 potionWeights=on"
cd "$REPO" || exit 2
for ((i = 0; i < 3; i++)); do
  arm=${ARMS[$(( (i + SEED) % 3 ))]}
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}")
  case $arm in
    P1) E+=("STS_SILVER_POTION_WEIGHTS=*=3.7,FAIRY_POTION=47.6" STS_SILVER_MAXHP_WEIGHT=2.4 STS_SILVER_GOLD_WEIGHT=0.12) ;;
    PF) E+=("STS_SILVER_POTION_WEIGHTS=*=11,FAIRY_POTION=47.6" STS_SILVER_MAXHP_WEIGHT=2.4 STS_SILVER_GOLD_WEIGHT=0.12) ;;
  esac
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 1000 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?; abort=0
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/net-0420.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims 1000 " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    grep -q "flat budget" "$b.log" "$b.err" || rc=92
    ! grep -q "tiered sims" "$b.log" "$b.err" || rc=90
    grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" "$b.log" "$b.err" || rc=89
    if [ "$arm" = D ]; then
      ! grep -q "\[silver\] research leaf" "$b.log" "$b.err" || rc=87
    else
      grep -qF "$BANNER" "$b.log" "$b.err" || rc=87
    fi
    ! grep -q "max backup\|risk veto\|price table" "$b.log" "$b.err" || rc=86
    # A combat stall ends the game as a loss (rc 0, CombatAbort) before the [heart1_ppo] game line is printed.
    abort=0; grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
    [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=${abort:-0}" > "$b.done"
done
exit 0
