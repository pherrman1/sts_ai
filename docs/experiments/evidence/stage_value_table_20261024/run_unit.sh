#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT DECK -- one Heart entry deck (DECK 0..391, deckIndex in variants.jsonl.gz):
# the base deck and its 24 variants, each replayed by act4replay at flat 10,000 simulations, 4 copies. Base and
# variants share battle and planner seeds: copy r uses battle seed 111303000 + 4 * DECK + r. Combat = arm P of
# act4_combat_strength_20261024 (g7f_E root/tree prior, greedy root-table playouts, no prior playouts).
# Always exits 0 (rc in the .done line). PREREG.md has the full config and provenance.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 DECK=$4
BASE=111303000 COPIES=4 VARIANTS=25
[[ $DECK =~ ^[0-9]+$ ]] && [ "$DECK" -lt 392 ] || { echo "bad deck $DECK" >&2; exit 2; }
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_FAIR=1 STS_COLLECT_KEYS=1 STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0 STS_SILVER_PRIOR_PLAYOUT_ELITE=0)
b=$OUT/deck-$DECK
# The deck's 25 state lines, in variantIndex order.
python3 -I - "$D/variants.jsonl.gz" "$DECK" "$b" <<'PY' || { echo "tag=deck-$DECK rc=3" > "$b.done"; exit 0; }
import gzip, json, sys
src, deck, b = sys.argv[1], int(sys.argv[2]), sys.argv[3]
lines = [json.loads(l) for l in gzip.open(src) if json.loads(l)['deckIndex'] == deck]
assert [l['variantIndex'] for l in lines] == list(range(25)), 'variant lines'
for l in lines:
    with open(f"{b}.v{l['variantIndex']:02d}.state.jsonl", 'w') as f:
        f.write(json.dumps(l['state']) + '\n')
PY
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s); rc=0
for ((v = 0; v < VARIANTS; v++)); do
  p=$b.v$(printf %02d $v)
  [ -s "$p.csv" ] && [ "$(tail -n +2 "$p.csv" | wc -l)" = $COPIES ] && continue  # resumed unit
  rm -f "$p.csv"
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" act4replay 1 "$p.state.jsonl" "$p" \
    $((BASE + DECK * COPIES)) 10000 $COPIES > "$p.log" 2> "$p.err"
  r=$?
  if [ "$r" = 0 ]; then
    # 4 data rows, none with an error (an invalid fight is kept and counted by the analysis).
    [ "$(tail -n +2 "$p.csv" | wc -l)" = $COPIES ] && ! grep -q ',ERROR,' "$p.csv" || r=91
    grep -q "Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8" "$p.log" "$p.err" || r=90
    grep -q "rollout root table model loaded: models/combat_policy_mlp_g7f_E.txt" "$p.log" "$p.err" || r=89
  fi
  [ "$r" = 0 ] || rc=$r
done
echo "tag=deck-$DECK rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
exit 0
