#!/usr/bin/env bash
# Learned budget step B (PREREG.md): one unit = one A20 run of `one_combat selffights` on one seed of the frozen
# block 111970000-111970255, through act ACT (the run stops at the first out-of-combat decision after it). The main line is §792's H4 combat (whole-run Gumbel root k 16, max
# backup 4, 16,000 simulations, 4,000 in Act 1-3 hallway fights, no prior playouts in boss/elite rooms) with LONG_C's
# net-0420 out of combat (temperature 0, no OOC MCTS), as §792/§795. In act ACT, every fight (all rooms) is an arm
# fight: the budget ladder gsh16+flat{1000,2000,4000,8000,16000}+mb4 plays copies 0-3 on the same copy seeds;
# production plays only the copies the main line needs (STS_SELF_FIGHTS_PROD=main).
# usage: run_unit.sh REPO RUN UNIT_OUT SEED ACT
# Exits 0 (rc in the .done line), except exit 3 when one_combat was killed by a signal (rc 137/143, issue #1001), so
# the queue re-runs the unit as a new attempt. A timeout (rc 124) is final.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4 ACT=${5:-}
[[ "$ACT" =~ ^[123]$ ]] || { echo "bad act '$ACT'" >&2; exit 2; }
if ! { [[ "$SEED" =~ ^[0-9]+$ ]] && [ "$SEED" -ge 111970000 ] && [ "$SEED" -le 111970255 ]; }; then
  echo "seed $SEED outside the frozen block 111970000-111970255" >&2; exit 2
fi
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
ARMS=gsh16+flat1000+mb4,gsh16+flat2000+mb4,gsh16+flat4000+mb4,gsh16+flat8000+mb4,gsh16+flat16000+mb4
mkdir -p "$OUT"
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0 STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_MCTS=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0
  "STS_OOC_HEART1=$RUN/net-0420.bin"
  STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4 STS_SILVER_GUMBEL_ROOT_SIMS=16000
  STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY=4000
  STS_SELF_FIGHTS_REPLICATES=4 "STS_SELF_FIGHTS_MAX_ACT=$ACT" "STS_SELF_FIGHTS_ARMS=$ARMS"
  "STS_SELF_FIGHTS_ARM_ROOMS=${ACT}M,${ACT}E,${ACT}B,${ACT}?" STS_SELF_FIGHTS_ARM_REPLICATES=4
  STS_SELF_FIGHTS_PROD=main)
cd "$REPO" || exit 2
TAG=L-$SEED-a$ACT
b=$OUT/$TAG
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 10h bash tools/seed_guard.sh "$RUN/one_combat" selffights 1 "$SEED" "$b.fights.json" \
  > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -qF "[heart1] loaded $RUN/net-0420.bin " "$b.log" "$b.err" || rc=95
  grep -q "learned stop gbt-0cac7cc64364" "$b.log" "$b.err" || rc=94
  grep -q '"schema":"self-fights-v1"' "$b.fights.json" || rc=93
  grep -qF "[silver] research search: whole-run Gumbel root k=16 max backup=4 (all acts, sims 16000, hallway sims 4000)" "$b.log" "$b.err" || rc=87
  grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
  grep -q "^\[selffights\] seed=$SEED " "$b.log" || rc=92
  ! grep -q "prior playouts only in acts\|combat net\|plan commit\|Gumbel learned stop" "$b.log" "$b.err" || rc=86
fi
echo "tag=$TAG rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
case $rc in 137|143) exit 3 ;; esac
exit 0
