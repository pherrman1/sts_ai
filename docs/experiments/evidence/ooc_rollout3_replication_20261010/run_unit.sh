#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN OUT ARM LO N   -- one guarded bestbench unit; resumable via OUT/ARM-LO.done
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 LO=$5 N=$6
base=$OUT/$ARM-$LO
[ -f "$base.done" ] && exit 0
if compgen -G "$base.*" > /dev/null; then          # interrupted unit: keep its files, rerun it whole
  ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$base".* "$OUT/aborted-$ts/"
  echo "$ARM-$LO moved to aborted-$ts" >> "$OUT/RESTARTS.txt"
fi
source "$REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
mapfile -t E < <(arm_env_args "$ARM" "$base" "$RUN") || exit 2
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 "$N" 0 "$LO" "$base.csv" > "$base.log" 2>&1
rc=$?
echo "tag=$ARM-$LO rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
