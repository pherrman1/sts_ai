#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT FIRST_SEED -- one unit of E1-R of the learned price head (PREREG.md): sixteen
# source seeds FIRST_SEED..FIRST_SEED+15 of the leaf pilot's first block (E1's units),
# `one_combat fightendpairgen 16 FIRST 1000 20 OUT n=0,ooc=ppo,rewards=1 -`.
# Each source run is E1's (net-0420 as the whole out-of-combat policy, combat B), without forks or fight replays; the
# source row logs every combat reward's potion roll (reward luck). Environment: exactly E1's
# ../learned_price_head_e1_20261107/run_unit.sh (the pilot's).
# Exits 0 when every check passed (UNIT_OUT/result.txt holds rc).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 FIRST=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = 767a44b222780dd5 ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
if ! { [ "$FIRST" -ge 111780000 ] && [ "$FIRST" -le 111788176 ] && [ $(( (FIRST - 111780000) % 16 )) = 0 ]; }; then
  echo "seed $FIRST outside the frozen block" >&2; exit 2
fi
N=16
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
b=$OUT/lr-$FIRST
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" fightendpairgen "$N" "$FIRST" 1000 20 \
  "$b.jsonl" "n=0,ooc=ppo,rewards=1" - > "$b.log" 2> "$b.err"
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
  python3 -I - "$b.jsonl" "$FIRST" <<'PY' || rc=88
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
first = int(sys.argv[2])
assert all(r['kind'] == 'source' for r in rows), 'unexpected row kind'
src = {r['seed']: r for r in rows}
assert sorted(src) == list(range(first, first + 16)), 'source seeds'
for seed, s in src.items():
    assert s['ppo']['decisions'] > 0, 'source run without net decisions'
    assert s['sampled'] == 0 and 'luck' not in s, 'forks or luck in an E1-R unit'
    log = s['rewards']
    assert log['inconsistent'] == 0, 'reward roll disagrees with the engine'
    for x in log['rolls']:
        assert 0 <= x['chance'] <= 100 and ('potion' in x) == x['dropped'], 'reward roll'
        assert not (x['dropped'] and x['chance'] == 0) and not (not x['dropped'] and x['chance'] == 100), 'roll'
    assert len(log['rolls']) <= s['fightEnds'], 'more rolls than won fights'
PY
fi
[ "$rc" = 0 ] && gzip -n -9 "$b.jsonl"
echo "tag=$FIRST rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/result.txt"
# rc != 0: the unit is not done; the queue retries it (at most four attempts in all).
[ "$rc" = 0 ]
