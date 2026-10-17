#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN OUT ARM ASC SEED -- one guarded one-seed bestbench unit (4 h timeout: rc 124); resumable via OUT/ARM-aASC-SEED.done
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 ASC=$5 SEED=$6
case $ARM in C|S|S3) ;; *) echo "unknown arm $ARM" >&2; exit 2 ;; esac
[ "$ASC" = 20 ] || { echo "ascension must be 20" >&2; exit 2; }
base=$OUT/$ARM-a$ASC-$SEED
[ -f "$base.done" ] && exit 0
if compgen -G "$base.*" > /dev/null; then          # interrupted unit: keep its files, rerun it whole
  ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$base".* "$OUT/aborted-$ts/"
  echo "$ARM-a$ASC-$SEED moved to aborted-$ts" >> "$OUT/RESTARTS.txt"
fi
source "$REPO/docs/experiments/evidence/rollout_student_leaf_20261017/arm_env.sh"
mapfile -t E < <(arm_env_args "$ARM" "$base" "$RUN") || exit 2
[ "${#E[@]}" -gt 30 ] || { echo "arm env incomplete" >&2; exit 2; }
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 "$ASC" "$SEED" "$base.csv" > "$base.log" 2>&1
rc=$?
echo "tag=$ARM-a$ASC-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
