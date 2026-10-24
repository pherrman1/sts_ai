#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT ENC STATE ARM -- one recorded Act-4 entry state (ENC ss|heart, STATE 0..127 = line
# STATE+1 of states/<enc>_128.jsonl) replayed by act4replay under one Silver arm, 8 copies at flat 10,000 and 40,000
# simulations (paired: same battle and planner seeds in every arm and budget). Always exits 0 (rc in the .done line).
# PREREG.md has the full config and provenance.
#   P   g7f_E root/tree prior (weight 400, tree prior K 8), greedy root-table playouts (production in elite rooms).
#   PP  P + prior playouts in every room (production in boss rooms, ADR-0050; STS_SILVER_PRIOR_PLAYOUT_ELITE=1 here).
#   N   no root/tree prior; greedy root-table playouts.
# Battle seed of copy r: 111395000 + STATE*8 + r (Shield and Spear), 111398100 + STATE*8 + r (the Heart).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ENC=$4 STATE=$5 ARM=$6
case $ENC in
  ss) FILE=states/shield_and_spear_128.jsonl BASE=111395000;;
  heart) FILE=states/the_heart_128.jsonl BASE=111398100;;
  *) echo "bad encounter $ENC" >&2; exit 2;;
esac
[[ $STATE =~ ^[0-9]+$ ]] && [ "$STATE" -lt 128 ] || { echo "bad state $STATE" >&2; exit 2; }
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_FAIR=1 STS_COLLECT_KEYS=1 STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt)
PRIOR=(STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8)
case $ARM in
  P)  E=("${COMMON[@]}" "${PRIOR[@]}" STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0 STS_SILVER_PRIOR_PLAYOUT_ELITE=0);;
  PP) E=("${COMMON[@]}" "${PRIOR[@]}" STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=1 STS_SILVER_PRIOR_PLAYOUT_ELITE=1);;
  N)  E=("${COMMON[@]}");;
  *) echo "bad arm $ARM" >&2; exit 2;;
esac
b=$OUT/$ENC-$STATE-$ARM
sed -n "$((STATE + 1))p" "$D/$FILE" > "$b.state.jsonl"
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" act4replay 1 "$b.state.jsonl" "$b" \
  $((BASE + STATE * 8)) 10000,40000 8 > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  # 16 data rows (8 copies x 2 budgets), none with an error (an invalid fight is kept and counted by the analysis).
  [ "$(tail -n +2 "$b.csv" | wc -l)" = 16 ] && ! grep -q ',ERROR,' "$b.csv" || rc=91
  # The prior banner must match the arm.
  case $ARM in
    N) ! grep -q "Silver root prior ON" "$b.log" "$b.err" || rc=90;;
    *) grep -q "Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8" "$b.log" "$b.err" || rc=90;;
  esac
  grep -q "rollout root table model loaded: models/combat_policy_mlp_g7f_E.txt" "$b.log" "$b.err" || rc=89
fi
echo "tag=$ENC-$STATE-$ARM rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
exit 0
