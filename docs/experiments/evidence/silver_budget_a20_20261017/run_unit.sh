#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN OUT ARM SEED -- one guarded one-seed A20 bestbench unit (2 h timeout: rc 124); resumable via OUT/ARM-SEED.done
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 SEED=$5
case $ARM in F|L|LP) ;; *) echo "unknown arm $ARM" >&2; exit 2 ;; esac
base=$OUT/$ARM-$SEED
[ -f "$base.done" ] && exit 0
if compgen -G "$base.*" > /dev/null; then          # interrupted unit: keep its files, rerun it whole
  ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$base".* "$OUT/aborted-$ts/"
  echo "$ARM-$SEED moved to aborted-$ts" >> "$OUT/RESTARTS.txt"
fi
source "$REPO/docs/experiments/evidence/silver_budget_a20_20261017/arm_env.sh"
mapfile -t E < <(arm_env_args "$ARM" "$base" "$RUN") || exit 2
[ "${#E[@]}" -ge 17 ] || { echo "arm env incomplete" >&2; exit 2; }
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 20 "$SEED" "$base.csv" > "$base.log" 2> "$base.err"
rc=$?
echo "tag=$ARM-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
