#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED SET -- the A20 games of one seed of the whole-run Gumbel teacher test
# (PREREG.md): SET low = arms D, G16, G32 (in an order rotated by seed), SET G64 = arm G64 (two units per seed balance
# the lanes and keep the share's file count down).
# LONG_C's net-0420 as the whole out-of-combat policy (temperature 0, no OOC MCTS), as §767; combat arms:
#   D    = today's A20 combat default: learned Silver stop (gbt-0cac7cc64364), exact root budgets, g7f_E root table +
#          prior (weight 400), tree prior K = 8, boss-only prior playouts, Act 4 strong; bestbench 10000.
#   G16 / G32 / G64 = D, except that every fight searches each root with the Gumbel root (k 16, §770) at a flat
#          16,000 / 32,000 / 64,000 simulations plus max backup (min 4 visits) (STS_SILVER_GUMBEL_ROOT=16,
#          STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4); in Act 4 at the larger of that and Act 4 strong's budget (S&S 10k,
#          Heart 40k), with Act 4 strong's prior playouts.
# Exits 0; the game's ARM-SEED.done holds its rc.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 SET=$5
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
if ! { [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; } && ! { [ "$SEED" -ge 111379280 ] && [ "$SEED" -le 111379289 ]; }; then
  echo "seed $SEED outside the frozen block" >&2; exit 2
fi
case $SET in
  low) L=(D G16 G32); ARMS=("${L[@]:$(( SEED % 3 ))}" "${L[@]:0:$(( SEED % 3 ))}") ;;
  G64) ARMS=(G64) ;;
  *) echo "bad set $SET" >&2; exit 2 ;;
esac
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_MCTS=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  "STS_OOC_HEART1=$RUN/net-0420.bin")
BANNER="[silver] research search: whole-run Gumbel root k=16 max backup=4 (all acts)"
cd "$REPO" || exit 2
for ARM in "${ARMS[@]}"; do
  case $ARM in
    D) SIMS=10000; X=() ;;
    *) SIMS=${ARM#G}000; X=(STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4) ;;
  esac
  E=("${COMMON[@]}" "${X[@]}")
  b=$OUT/$ARM-$SEED
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 8h bash tools/seed_guard.sh "$RUN/one_combat" bestbench "$SIMS" 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?; abort=0
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/net-0420.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims $SIMS " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    grep -q "learned stop gbt-0cac7cc64364" "$b.log" "$b.err" || rc=92
    grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" "$b.log" "$b.err" || rc=89
    if [ "$ARM" = D ]; then
      ! grep -q "whole-run Gumbel root" "$b.log" "$b.err" || rc=87
    else
      grep -qF "$BANNER" "$b.log" "$b.err" || rc=87
      grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
    fi
    ! grep -q "research search: max backup min visits\|risk veto\|price table\|research leaf" "$b.log" "$b.err" || rc=86
    # A combat stall ends the game as a loss (rc 0, CombatAbort) before the [heart1_ppo] game line is printed.
    grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
    [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
  fi
  echo "tag=$ARM-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=$abort" > "$b.done"
done
exit 0
