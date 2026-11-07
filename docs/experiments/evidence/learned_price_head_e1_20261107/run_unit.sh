#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT FIRST_SEED -- one unit of E1 of the learned price head (PREREG.md): sixteen
# source seeds FIRST_SEED..FIRST_SEED+15 of the leaf pilot's first block,
# `one_combat fightendpairgen 16 FIRST 1000 20 OUT n=0,ooc=ppo,luck=1,luck_identity=1 -`.
# Each source run is the leaf pilot's (net-0420 as the whole out-of-combat policy, combat B), without forks; every
# fight is replayed once on fresh streams (fight luck), and the unit's first seed also replays each fight unchanged
# (identity check). Environment: exactly the pilot's ../fight_end_pairs_pilot_20261107/run_unit.sh.
# Exits 0 when every check passed (UNIT_OUT/result.txt holds rc).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 FIRST=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = 26775caf3c986e38 ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
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
b=$OUT/le-$FIRST
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" fightendpairgen "$N" "$FIRST" 1000 20 \
  "$b.jsonl" "n=0,ooc=ppo,luck=1,luck_identity=1" - > "$b.log" 2> "$b.err"
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
import collections, json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
first = int(sys.argv[2])
src = {r['seed']: r for r in rows if r['kind'] == 'source'}
luck = collections.defaultdict(list)
for r in rows:
    assert r['kind'] in ('source', 'luck'), 'unexpected row kind ' + r['kind']
    if r['kind'] == 'luck':
        luck[r['seed']].append(r)
assert sorted(src) == list(range(first, first + 16)), 'source seeds'
replays = errors = 0
for seed, s in src.items():
    assert s['ppo']['decisions'] > 0, 'source run without net decisions'
    assert s['sampled'] == 0, 'forks in an E1 unit'
    l = s['luck']
    fights = luck[seed]
    assert l['fights'] == len(fights) and l['fights'] in (s['fightEnds'], s['fightEnds'] + 1), 'luck rows per seed'
    assert [f['fightIndex'] for f in fights] == list(range(len(fights))), 'luck fight order'
    assert l['identitySeed'] == (seed == first), 'identity seed'
    assert l['replays'] == len(fights) * (2 if seed == first else 1), 'replay count'
    for f in fights:
        assert len(f['replays']) == 1 and f['replays'][0]['r'] == 1, 'one fresh replay per fight'
        assert ('identity' in f) == (seed == first), 'identity field'
    replays += l['replays']
    errors += l['errors']
assert errors <= 0.05 * replays, 'replay errors above 5%'
PY
fi
[ "$rc" = 0 ] && gzip -n -9 "$b.jsonl"
echo "tag=$FIRST rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/result.txt"
# rc != 0: the unit is not done; the queue retries it (at most four attempts in all).
[ "$rc" = 0 ]
