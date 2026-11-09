#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED trio -- the three A20 games of one seed of the Gumbel budget-curve test
# (PREREG.md), in an order rotated by seed:
#   G2 / G4 / G8 = ../gumbel_1k_wholerun_20261109's G1 (combat B plus the Gumbel root k 16 with max backup 4 in every
#        fight, Act 4 included, Act 4 strong off) at bestbench 2000 / 4000 / 8000 simulations. Nothing else changes;
#        the 1k test's B1 and G1 games (same binary, same seeds) are the comparison arms.
# LONG_C's net-0420 as the whole out-of-combat policy (temperature 0, no OOC MCTS), as §775 and §777.
# Exits 0 (each game's ARM-SEED.done holds its rc), except when a game was killed by a signal (rc 137/143, issue #1001):
# then exit 3, so the queue re-runs the unit as a new attempt. A timeout (rc 124) is final and counts as a drop.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 SET=$5
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
if ! { [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111378767 ]; }; then
  echo "seed $SEED outside the first 512 seeds of §775's frozen block" >&2; exit 2
fi
[ "$SET" = trio ] || { echo "bad set $SET" >&2; exit 2; }
L=(G2 G4 G8); ARMS=("${L[@]:$(( SEED % 3 ))}" "${L[@]:0:$(( SEED % 3 ))}")
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0
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
killed=0
for ARM in "${ARMS[@]}"; do
  SIMS=${ARM#G}000
  X=(STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4)
  E=("${COMMON[@]}" "${X[@]}")
  b=$OUT/$ARM-$SEED
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" bestbench "$SIMS" 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?; abort=0
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/net-0420.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims $SIMS " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    ! grep -q "tiered sims" "$b.log" "$b.err" || rc=90
    grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" "$b.log" "$b.err" || rc=89
    grep -qF "$BANNER" "$b.log" "$b.err" || rc=87
    grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
    grep -q "^\[silver\] whole-run tree reuse: .* reuse_cap=32768$" "$b.err" || rc=84
    ! grep -q "research search: max backup min visits\|risk veto\|price table\|research leaf\|whole-run Gumbel tree\|research node reuse cap" "$b.log" "$b.err" || rc=86
    # A combat stall ends the game as a loss (rc 0, CombatAbort) before the [heart1_ppo] game line is printed.
    grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
    [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
  fi
  echo "tag=$ARM-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=$abort" > "$b.done"
  case $rc in 137|143) killed=1 ;; esac
done
[ "$killed" = 0 ] || exit 3
exit 0
