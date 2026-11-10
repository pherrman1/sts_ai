#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT LABEL SEED... -- traced replay of the §775 games of the unit's seeds (PREREG.md;
# units.txt packs consecutive seeds into units of about 1 h, make_units.py): per seed arms D and G16
# exactly as in docs/experiments/evidence/gumbel_wholerun_20261108/run_unit.sh (same binary 0eabb014, same environment,
# same net-0420), plus STS_OOC_DECISION_TRACE, which only reads state: one JSON line per out-of-combat step and per
# battle (encounter, room, won, turns, HP / max HP / gold / deck / relics / potions before and after). The trace is
# gzipped as ARM-SEED.trace.jsonl.gz next to ARM-SEED.{done,log,err,env}.
# Exits 0 (each game's ARM-SEED.done holds its rc), except when a game was killed by a signal (rc 137/143, issue #1001):
# then exit 3, so the queue re-runs the unit as a new attempt. A timeout (rc 124) is final and counts as a drop.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 LABEL=$4
shift 4
[[ "$LABEL" =~ ^p[0-9]{3}$ ]] || { echo "bad unit label $LABEL" >&2; exit 2; }
[ $# -ge 1 ] || { echo "no seeds" >&2; exit 2; }
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
for SEED in "$@"; do
  if ! { [[ "$SEED" =~ ^[0-9]+$ ]] && [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; }; then
    echo "seed $SEED outside the §775 block" >&2; exit 2
  fi
done
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
  "STS_OOC_HEART1=$RUN/net-0420.bin")
BANNER="[silver] research search: whole-run Gumbel root k=16 max backup=4 (all acts)"
cd "$REPO" || exit 2
killed=0
for SEED in "$@"; do
for ARM in D G16; do
  case $ARM in
    D) SIMS=10000; X=() ;;
    G16) SIMS=16000; X=(STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4) ;;
  esac
  b=$OUT/$ARM-$SEED
  rm -f "$b.trace.jsonl" "$b.trace.jsonl.gz"
  E=("${COMMON[@]}" "${X[@]}" "STS_OOC_DECISION_TRACE=$b.trace.jsonl")
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
    if [ "$ARM" = D ]; then
      ! grep -q "whole-run Gumbel root" "$b.log" "$b.err" || rc=87
    else
      grep -qF "$BANNER" "$b.log" "$b.err" || rc=87
      grep -q "^\[silver\] whole-run Gumbel roots=[1-9]" "$b.err" || rc=85
    fi
    ! grep -q "research search: max backup min visits\|risk veto\|price table\|research leaf" "$b.log" "$b.err" || rc=86
    # A combat stall ends the game as a loss (rc 0, CombatAbort) before the [heart1_ppo] game line is printed.
    grep -q "^\[bestbench-combat-abort\] seed=$SEED " "$b.err" && abort=1
    [ "$abort" = 1 ] || grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
    grep -q '"kind":"battle"' "$b.trace.jsonl" 2>/dev/null || rc=84
  fi
  [ -f "$b.trace.jsonl" ] && gzip -n -9 "$b.trace.jsonl"
  echo "tag=$ARM-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 )) abort=$abort" > "$b.done"
  case $rc in 137|143) killed=1; break 2 ;; esac
done
done
[ "$killed" = 0 ] || exit 3
exit 0
