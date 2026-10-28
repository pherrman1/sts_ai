#!/usr/bin/env bash
# usage: run_all.sh REPO RUN OUT UNITS [LANES=4] -- runs run_unit.sh for every seed in UNITS, LANES at a time, on this
# host; one OUT/SEED directory per seed; skips seeds whose two .done files already exist (restartable).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 UNITS=$4 LANES=${5:-4}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
grep -v '^#' "$UNITS" | while read -r s; do
  [ -s "$OUT/$s/A-$s.done" ] && [ -s "$OUT/$s/B-$s.done" ] && continue
  echo "$s"
done | xargs -P "$LANES" -I{} bash "$HERE/run_unit.sh" "$REPO" "$RUN" "$OUT/{}" {}
