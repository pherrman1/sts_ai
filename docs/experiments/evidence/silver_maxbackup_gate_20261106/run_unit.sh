#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the STS_SILVER_MAX_BACKUP=4 gate (PREREG.md).
# LONG_B's evaluation runner (../ppo_long_b_20261104/eval/run_unit.sh) with LONG_B's net-0220 only (policy alone,
# temperature 0, no OOC MCTS, flat Silver 1,000, learned stop off) and two arms on every seed:
#   D = the default (mean backup),  M = D + STS_SILVER_MAX_BACKUP=4.
# Order rotated by seed. Exits 0.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = @BIN16@ ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/l220.bin" | cut -c1-16)" = 408b2982a1a8757f ] || { echo "bad $RUN/l220.bin" >&2; exit 2; }
if ! { [ "$SEED" -ge 111760000 ] && [ "$SEED" -le 111762047 ]; } && ! { [ "$SEED" -ge 111769990 ] && [ "$SEED" -le 111769999 ]; }; then
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
  "STS_OOC_HEART1=$RUN/l220.bin")
ARMS=(D M)
cd "$REPO" || exit 2
for ((i = 0; i < 2; i++)); do
  arm=${ARMS[$(( (i + SEED) % 2 ))]}
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}")
  [ "$arm" = M ] && E+=(STS_SILVER_MAX_BACKUP=4)
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 1000 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?; abort=0
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/l220.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims 1000 " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    grep -q "flat budget" "$b.log" "$b.err" || rc=92
    ! grep -q "tiered sims" "$b.log" "$b.err" || rc=90
    grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" "$b.log" "$b.err" || rc=89
    if [ "$arm" = M ]; then
      grep -qF "[silver] research search: max backup min visits=4" "$b.log" "$b.err" || rc=87
    else
      ! grep -q "max backup" "$b.log" "$b.err" || rc=86
    fi
    ! grep -q "\[silver\] research leaf" "$b.log" "$b.err" || rc=85
    # A combat stall ends the game as a loss (rc 0, CombatAbort) before the [heart1_ppo] game line is printed.
    abort=0; grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
    [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=${abort:-0}" > "$b.done"
done
exit 0
