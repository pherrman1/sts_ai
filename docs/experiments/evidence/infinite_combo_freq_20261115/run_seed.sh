#!/usr/bin/env bash
# usage: run_seed.sh REPO RUN OUT SEED -- replay of the §775 G16 + mb4 game of SEED (same environment as
# docs/experiments/evidence/gumbel_wholerun_20261108/run_unit.sh, net-0420, binary built from code with only the
# read-only STS_COMBAT_STATE_CAPTURE observer added), writing OUT/G16-SEED.{log,err,env,done} and the turn-start
# snapshots OUT/G16-SEED.states.jsonl.gz. Seeds must lie in the §775 block (no new seeds).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
{ [[ "$SEED" =~ ^[0-9]+$ ]] && [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; } || { echo "seed $SEED outside the §775 block" >&2; exit 2; }
mkdir -p "$OUT"
b=$OUT/G16-$SEED
[ -f "$b.done" ] && grep -q "rc=0 " "$b.done" && exit 0
rm -f "$b.states.jsonl" "$b.states.jsonl.gz"
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$RUN/src" rev-parse HEAD 2>/dev/null || echo unknown)"
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
  STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4
  "STS_COMBAT_STATE_CAPTURE=$b.states.jsonl")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 8h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 16000 1 20 "$SEED" > "$b.log" 2> "$b.err"
rc=$?
if [ "$rc" = 0 ]; then
  grep -q "^BEST  *win%=" "$b.log" || rc=93
  grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
  grep -q '"kind":"fight"' "$b.states.jsonl" 2>/dev/null || rc=84
fi
[ -f "$b.states.jsonl" ] && gzip -n -6 "$b.states.jsonl"
echo "tag=G16-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
