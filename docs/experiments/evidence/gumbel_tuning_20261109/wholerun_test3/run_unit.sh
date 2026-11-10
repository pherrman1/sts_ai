#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED SET -- one A20 game of the whole-run c2 test (../wholerun/PREREG.md) or
# its Test 2 / Test 3, SET = its arm:
#   C2    = §775's G16 + mb4 (gumbel_wholerun_20261108/run_unit.sh), plus Gumbel tuning stage 2's pick c2's tree
#           settings in every fight: UCB exploration 12.5 (STS_SILVER_GUMBEL_ROOT_UCB), root prior weight 100 instead
#           of 400 (STS_SILVER_ROOT_PRIOR_WEIGHT), tree prior from 32 instead of 8 visits
#           (STS_SILVER_TREE_PRIOR_MIN_VISITS), widening C 14.8 at end-turn and 1.85 at other chance nodes
#           (STS_SILVER_GUMBEL_ROOT_WIDEN_END_TURN / _WIDEN_CHANCE); bestbench 16000.
#   G16   = §775's G16 + mb4 unchanged (the control sentinel: these games must replay §775's G16 games exactly).
#   C2CAP / G16CAP = C2 / G16 with node reuse cap 262144 instead of 32768 (STS_SILVER_NODE_REUSE_CAP; the Heart's
#           cap already): the node-cap test after the c2 test (PREREG "Test 2").
#   G16NR = G16 with node reuse cap 1024 (STS_SILVER_NODE_REUSE_CAP=1024, the smallest allowed): almost every reroot
#           outside the Heart starts a fresh tree; the Heart keeps its 262144 cap (Test 3, PREREG.md next to this copy).
# LONG_C's net-0420 as the whole out-of-combat policy (temperature 0, no OOC MCTS), as §775.
# Exits 0 (the game's ARM-SEED.done holds its rc), except when the game was killed by a signal (rc 137/143, issue
# #1001): then exit 3, so the queue re-runs the unit as a new attempt. A timeout (rc 124) is final and counts as a drop.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 SET=$5
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
if ! { [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; } && ! { [ "$SEED" -ge 111379280 ] && [ "$SEED" -le 111379289 ]; }; then
  echo "seed $SEED outside §775's frozen block" >&2; exit 2
fi
mkdir -p "$OUT"
ARM=$SET
G=(STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4)
C2=(STS_SILVER_GUMBEL_ROOT_UCB=12.5 STS_SILVER_GUMBEL_ROOT_WIDEN_END_TURN=14.8 STS_SILVER_GUMBEL_ROOT_WIDEN_CHANCE=1.85)
case $ARM in
  G16) PW=400 TP=8; X=("${G[@]}") ;;
  C2) PW=100 TP=32; X=("${G[@]}" "${C2[@]}") ;;
  C2CAP) PW=100 TP=32; X=("${G[@]}" "${C2[@]}" STS_SILVER_NODE_REUSE_CAP=262144) ;;
  G16CAP) PW=400 TP=8; X=("${G[@]}" STS_SILVER_NODE_REUSE_CAP=262144) ;;
  G16NR) PW=400 TP=8; X=("${G[@]}" STS_SILVER_NODE_REUSE_CAP=1024) ;;
  *) echo "bad set $SET" >&2; exit 2 ;;
esac
SIMS=16000
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
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
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=$PW
  STS_SILVER_TREE_PRIOR_MIN_VISITS=$TP
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  "STS_OOC_HEART1=$RUN/net-0420.bin" "${X[@]}")
cd "$REPO" || exit 2
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
  grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight $PW; tree prior K=$TP]" "$b.log" "$b.err" || rc=89
  grep -qF "[silver] research search: whole-run Gumbel root k=16 max backup=4 (all acts)" "$b.log" "$b.err" || rc=87
  grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
  grep -q "^\[silver\] whole-run tree reuse: reroots=[0-9]" "$b.err" || rc=84
  case $ARM in
    G16*) ! grep -q "whole-run Gumbel tree" "$b.log" "$b.err" || rc=83 ;;
    *) grep -qF "[silver] research search: whole-run Gumbel tree ucb=12.5 widen end turn=14.8 widen chance=1.85" "$b.log" "$b.err" || rc=83 ;;
  esac
  case $ARM in
    *CAP) grep -qF "[silver] research node reuse cap 262144" "$b.log" "$b.err" || rc=82
          grep -q "^\[silver\] whole-run tree reuse: .* reuse_cap=262144$" "$b.err" || rc=82 ;;
    G16NR) grep -qF "[silver] research node reuse cap 1024" "$b.log" "$b.err" || rc=82
           grep -q "^\[silver\] whole-run tree reuse: .* reuse_cap=1024$" "$b.err" || rc=82 ;;
    *) ! grep -q "research node reuse cap" "$b.log" "$b.err" || rc=82
       grep -q "^\[silver\] whole-run tree reuse: .* reuse_cap=32768$" "$b.err" || rc=82 ;;
  esac
  ! grep -q "research search: max backup min visits\|risk veto\|price table\|research leaf" "$b.log" "$b.err" || rc=86
  # A combat stall ends the game as a loss (rc 0, CombatAbort) before the [heart1_ppo] game line is printed.
  grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
  [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
fi
echo "tag=$ARM-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=$abort" > "$b.done"
case $rc in 137|143) exit 3 ;; esac
exit 0
