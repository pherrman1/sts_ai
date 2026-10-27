#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT CELL DECK -- one Heart entry deck (DECK 0..95) in one cell of the P300
# clairvoyance 2x2 (PREREG.md): its 12 fixed variants (11 when the deck has no Strike), each replayed by act4replay
# with 4 copies. Copy r of every variant and every cell uses battle seed 111304600 + 4 * DECK + r.
# CELL: Fnat / Ffull = fair Silver P10k (arm P of act4_combat_strength_20261024, as #855 Stage A);
#       Knat / Kfull = STS_ACT4REPLAY_COMBAT=known (ADR-0062) at 8,000 sims x Boss multiplier 3.
# nat keeps the natural entry HP; full sets hp = maxHp. Always exits 0 (rc in the .done line).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 CELL=$4 DECK=$5
BASE=111304600 COPIES=4
[[ $DECK =~ ^[0-9]+$ ]] && [ "$DECK" -lt 96 ] || { echo "bad deck $DECK" >&2; exit 2; }
case $CELL in Fnat|Ffull) SIMS=10000 ;; Knat|Kfull) SIMS=8000 ;; *) echo "bad cell $CELL" >&2; exit 2 ;; esac
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
case $CELL in K*) E+=(STS_ACT4REPLAY_COMBAT=known) ;; esac
b=$OUT/$CELL-deck-$DECK
# The deck's state lines, in variantIndex order, with full HP for the *full cells.
python3 -I - "$D/states.jsonl.gz" "$DECK" "$b" "$CELL" <<'PY' || { echo "tag=$CELL-deck-$DECK rc=3" > "$b.done"; exit 0; }
import gzip, json, sys
src, deck, b, cell = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
lines = [json.loads(l) for l in gzip.open(src)]
lines = [l for l in lines if l['deckIndex'] == deck]
v = [l['variantIndex'] for l in lines]
assert v in (list(range(12)), list(range(11))), 'variant lines'
for l in lines:
    s = l['state']
    if cell.endswith('full'):
        s['hp'] = s['maxHp']
    with open(f"{b}.v{l['variantIndex']:02d}.state.jsonl", 'w') as f:
        f.write(json.dumps(s) + '\n')
PY
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s); rc=0
for s in "$b".v*.state.jsonl; do
  p=${s%.state.jsonl}
  [ -s "$p.csv" ] && [ "$(tail -n +2 "$p.csv" | wc -l)" = $COPIES ] && continue  # resumed unit
  rm -f "$p.csv"
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" act4replay 1 "$s" "$p" \
    $((BASE + DECK * COPIES)) $SIMS $COPIES > "$p.log" 2> "$p.err"
  r=$?
  if [ "$r" = 0 ]; then
    # 4 data rows, none with an error (an invalid fight is kept and counted by the analysis).
    [ "$(tail -n +2 "$p.csv" | wc -l)" = $COPIES ] && ! grep -q ',ERROR,' "$p.csv" || r=91
    case $CELL in
      F*) grep -q "Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8" "$p.log" "$p.err" || r=90
          grep -q "rollout root table model loaded: models/combat_policy_mlp_g7f_E.txt" "$p.log" "$p.err" || r=89
          [ "$(tail -n +2 "$p.csv" | cut -d, -f16 | sort -u)" = fair ] || r=88 ;;
      K*) [ "$(tail -n +2 "$p.csv" | cut -d, -f16 | sort -u)" = known_rng ] || r=88 ;;
    esac
  fi
  [ "$r" = 0 ] || rc=$r
done
echo "tag=$CELL-deck-$DECK rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
exit 0
