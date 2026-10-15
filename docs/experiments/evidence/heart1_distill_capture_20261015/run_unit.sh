#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN OUT ASC SEED -- one guarded one-seed bestbench unit of the §486 V4 arm with heart1
# distillation capture (4 h timeout: rc 124); resumable via OUT/cap-aASC-SEED.done. The capture is gzipped at the end.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ASC=$4 SEED=$5
case $ASC in 0|20) ;; *) echo "ascension must be 0 or 20" >&2; exit 2 ;; esac
base=$OUT/cap-a$ASC-$SEED
[ -f "$base.done" ] && exit 0
if compgen -G "$base.*" > /dev/null; then          # interrupted unit: keep its files, rerun it whole
  ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$base".* "$OUT/aborted-$ts/"
  echo "cap-a$ASC-$SEED moved to aborted-$ts" >> "$OUT/RESTARTS.txt"
fi
source "$REPO/docs/experiments/evidence/heart1_ooc_ab_486_20261015/arm_env.sh"
mapfile -t E < <(arm_env_args v4 "$base" "$RUN") || exit 2
[ "${#E[@]}" -gt 20 ] || { echo "arm env incomplete" >&2; exit 2; }
E+=("STS_OOC_HEART1=$RUN/heart1.bin" "STS_OOC_HEART1_CAPTURE=$base.capture.jsonl" "STS_OOC_HEART1_CAPTURE_EVERY=8")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 "$ASC" "$SEED" "$base.csv" > "$base.log" 2>&1
rc=$?
[ -f "$base.capture.jsonl" ] && gzip -f "$base.capture.jsonl"
echo "tag=cap-a$ASC-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
