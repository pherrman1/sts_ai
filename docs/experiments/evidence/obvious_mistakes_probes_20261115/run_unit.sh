#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT LABEL PATTERN SEED INDEX SALT KEY -- one paired probe of issue #1056 (PREREG.md).
# Replays §782's G16 game SEED (the §775 arm exactly as gumbel_wholerun_trace_20261109/run_unit.sh: same environment,
# net-0420; binary = code ebd446b3 + the ppo: force key, which reproduces §782 without the flag) to out-of-combat
# decision INDEX and plays two games to the end: A = the PPO token KEY names (STS_OOC_FORCE_DECISION=INDEX:SALT:KEY),
# then B = the production choice (INDEX:SALT:-). Both redraw the hidden future with SALT after the decision, so A and B
# share it. If KEY matches no token at INDEX (e.g. every path leads to an elite), A stops there with
# "no_token_matches_"; the unit is then ineligible (A.done says ineligible=1) and B is not played.
# Read-only traces: STS_OOC_DECISION_TRACE and STS_OOC_HEART1_PPO_TRAJ (outcome, the forced decision).
# Exits 0 (each game's TAG.done holds its rc), except when a game was killed by a signal (rc 137/143, issue #1001):
# then exit 3, so the queue re-runs the unit. A timeout (rc 124) is final and counts as a drop.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 LABEL=$4 PATTERN=$5 SEED=$6 INDEX=$7 SALT=$8 KEY=$9
[[ "$LABEL" =~ ^u[0-9]{3}$ ]] || { echo "bad unit label $LABEL" >&2; exit 2; }
[[ "$PATTERN" =~ ^(smith|elite|corruption|runic)$ ]] || { echo "bad pattern $PATTERN" >&2; exit 2; }
{ [[ "$SEED" =~ ^[0-9]+$ ]] && [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; } || { echo "seed $SEED outside the §775 block" >&2; exit 2; }
[[ "$INDEX" =~ ^[0-9]+$ && "$SALT" =~ ^[1-9][0-9]*$ && "$KEY" =~ ^ppo:[a-z_]+=[0-9,]+$ ]] || { echo "bad index/salt/key" >&2; exit 2; }
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
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
for TAG in A B; do
  case $TAG in B) F="$INDEX:$SALT:-" ;; A) F="$INDEX:$SALT:$KEY" ;; esac
  b=$OUT/$TAG-$SEED-$INDEX
  [ -s "$b.done" ] && grep -q ' rc=0 ' "$b.done" && continue   # a re-run unit keeps finished games
  rm -f "$b".trace.jsonl* "$b".ppo.jsonl*
  E=("${COMMON[@]}" "STS_OOC_FORCE_DECISION=$F" "STS_OOC_DECISION_TRACE=$b.trace.jsonl" "STS_OOC_HEART1_PPO_TRAJ=$b.ppo.jsonl")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 16000 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?; abort=0; inel=0
  [ "$TAG" = A ] && [ "$rc" != 0 ] && grep -q "STS_OOC_FORCE_DECISION $KEY: no_token_matches_" "$b.err" && inel=1
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/net-0420.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims 16000 " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    grep -q "learned stop gbt-0cac7cc64364" "$b.log" "$b.err" || rc=92
    grep -qF "$BANNER" "$b.log" "$b.err" || rc=87
    grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
    [ "$abort" = 1 ] || grep -qE "^\[heart1_ppo\] seed=[0-9]+ decisions=" "$b.log" "$b.err" || rc=88   # the fork prints the redrawn seed
    if [ "$abort" = 0 ]; then
      grep -q '"type": *"game"' "$b.ppo.jsonl" 2>/dev/null || rc=84
      [ "$TAG" = B ] || grep -qF "\"forced\":\"$KEY\"" "$b.ppo.jsonl" || rc=83
    fi
  fi
  for f in "$b.trace.jsonl" "$b.ppo.jsonl"; do [ -f "$f" ] && gzip -n -9 -f "$f"; done
  echo "tag=$TAG-$SEED-$INDEX pattern=$PATTERN rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=$abort ineligible=$inel" > "$b.done"
  case $rc in 137|143) exit 3 ;; esac
  [ "$inel" = 1 ] && break
done
exit 0
