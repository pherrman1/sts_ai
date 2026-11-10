#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one A20 whole run of the §775 G16 arm (Gumbel root k 16, 16,000
# simulations, max backup 4, net-0420 OOC) with STS_SILVER_GUMBEL_STOP_TRACE on: training data for a learned stop
# at the Gumbel root's halving boundaries (SMOKE.md of gumbel_stop_trace_20261110, PREREG.md here).
# The environment is §775's G16 environment (gumbel_wholerun_20261108/run_unit.sh) plus the trace; the trace does
# not change play (18/18 identical replays, #1023). The trace CSV is stored xz-compressed as G16-SEED.csv.xz.
# Exits 0 (G16-SEED.done holds the rc), except when the game was killed by a signal (rc 137/143, issue #1001):
# then exit 3, so the queue re-runs the unit as a new attempt. A timeout (rc 124) is final and counts as a drop.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
if ! { [ "$SEED" -ge 111430000 ] && [ "$SEED" -le 111431023 ]; } && ! { [ "$SEED" -ge 111431100 ] && [ "$SEED" -le 111431109 ]; }; then
  echo "seed $SEED outside the frozen block" >&2; exit 2
fi
mkdir -p "$OUT"
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
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  "STS_OOC_HEART1=$RUN/net-0420.bin"
  STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4)
BANNER="[silver] research search: whole-run Gumbel root k=16 max backup=4 (all acts)"
cd "$REPO" || exit 2
SIMS=16000
b=$OUT/G16-$SEED
rm -f "$b.csv" "$b.csv.xz"
E+=("STS_SILVER_GUMBEL_STOP_TRACE=$b.csv")
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
  grep -qF "$BANNER" "$b.log" "$b.err" || rc=87
  grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
  ! grep -q "research search: max backup min visits\|risk veto\|price table\|research leaf" "$b.log" "$b.err" || rc=86
  grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
  [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
  # The trace has a header and at least one boundary row of this seed.
  { [ -s "$b.csv" ] && head -1 "$b.csv" | grep -q '^seed,combat,decision,' \
      && [ "$(awk -F, -v s="$SEED" 'NR>1 && $1==s' "$b.csv" | head -1 | wc -l)" = 1 ]; } || rc=84
fi
[ -f "$b.csv" ] && xz -T1 -6 "$b.csv"
echo "tag=G16-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=$abort" > "$b.done"
case $rc in 137|143) exit 3 ;; esac
exit 0
