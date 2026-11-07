#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT FIRST_SEED -- one unit of the stage-2 leaf pilot (PREREG.md): eight source
# seeds FIRST_SEED..FIRST_SEED+7, `one_combat fightendpairgen 8 FIRST_SEED 1000 20 OUT n=4,ooc=ppo default`.
# Policy = LONG_C's net-0420 as the whole out-of-combat policy (STS_OOC_HEART1_PPO=1, temperature 0, salt 0, no OOC
# MCTS); combat = combat B of LONG_B/LONG_C (flat Silver 1,000, learned stop off, Act-4 strong off, g7f_E root and
# tree prior): the environment of ../ppo_long_b_20261104/eval/run_unit.sh. Exits 0 when every check passed (UNIT_OUT/result.txt holds rc).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 FIRST=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = 968615927ae7fc8d ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
in_block() { [ "$FIRST" -ge "$1" ] && [ "$FIRST" -le "$2" ] && [ $(( (FIRST - $1) % 8 )) = 0 ]; }
if ! in_block 111780000 111788184 && ! in_block 111790000 111802280 \
    && ! { [ "$FIRST" -ge 111789990 ] && [ "$FIRST" -le 111789999 ]; }; then
  echo "seed $FIRST outside the frozen block" >&2; exit 2
fi
N=8; [ "$FIRST" -ge 111789990 ] && [ "$FIRST" -le 111789999 ] && N=1   # smoke seeds: one source seed
mkdir -p "$OUT"
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
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
b=$OUT/fe-$FIRST
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" fightendpairgen "$N" "$FIRST" 1000 20 \
  "$b.jsonl" "n=4,ooc=ppo" default > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -qF "[heart1] loaded $RUN/net-0420.bin " "$b.log" "$b.err" || rc=95
  [ -s "$b.jsonl.manifest.json" ] || rc=94
  [ "$(grep -c '"kind":"source"' "$b.jsonl")" = "$N" ] || rc=93
  [ "$(grep -c '^\[fightendpairgen\] seed=' "$b.log")" = "$N" ] || rc=92
  ! grep -q "\[silver\] research leaf" "$b.log" "$b.err" || rc=91
  ! grep -q "tiered sims" "$b.log" "$b.err" || rc=90
  grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" \
    "$b.log" "$b.err" || rc=89
  python3 -I - "$b.jsonl" <<'PY' || rc=88
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
assert all('ppo' in r for r in rows if r['kind'] in ('source', 'copy')), 'row without ppo counters'
assert all(r['ppo']['decisions'] > 0 for r in rows if r['kind'] == 'source'), 'source run without net decisions'
PY
fi
[ "$rc" = 0 ] && gzip -n -9 "$b.jsonl"
echo "tag=$FIRST rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/result.txt"
# rc != 0: the unit is not done; the queue retries it (at most four attempts in all).
[ "$rc" = 0 ]
