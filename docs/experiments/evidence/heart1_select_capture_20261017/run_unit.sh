#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN OUT MODE ASC SEED -- one guarded one-seed bestbench unit (4 h timeout: rc 124);
# resumable via OUT/MODE-aASC-SEED.done; the capture is gzipped at the end.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 MODE=$4 ASC=$5 SEED=$6
case $MODE in off|cap) ;; *) echo "unknown mode $MODE" >&2; exit 2 ;; esac
[ "$ASC" = 20 ] || { echo "ascension must be 20" >&2; exit 2; }
base=$OUT/$MODE-a$ASC-$SEED
[ -f "$base.done" ] && exit 0
if compgen -G "$base.*" > /dev/null; then          # interrupted unit: keep its files, rerun it whole
  ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$base".* "$OUT/aborted-$ts/"
  echo "$MODE-a$ASC-$SEED moved to aborted-$ts" >> "$OUT/RESTARTS.txt"
fi
source "$REPO/docs/experiments/evidence/heart1_select_capture_20261017/arm_env.sh"
mapfile -t E < <(capture_env_args "$MODE" "$base" "$RUN") || exit 2
[ "${#E[@]}" -gt 30 ] || { echo "env incomplete" >&2; exit 2; }
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 "$ASC" "$SEED" "$base.csv" > "$base.log" 2>&1
rc=$?
[ -f "$base.capture.jsonl" ] && gzip -f "$base.capture.jsonl"
echo "tag=$MODE-a$ASC-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
