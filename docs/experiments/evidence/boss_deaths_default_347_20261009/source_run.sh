#!/usr/bin/env bash
# Stage 1 (PLAN.md): default-stack bestbench on seeds 66000000..66000255,
# four shards of 64 seeds, one CPU each.
# Usage: source_run.sh BINARY BINARY_SHA256 EXEC_GIT_SHA OUT   (from the frozen plan commit)
set -u
SRC=$1 SHA=$2 EXEC_SHA=$3 OUT=$4
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
cd "$(git rev-parse --show-toplevel)"
EV=docs/experiments/evidence/boss_deaths_default_347_20261009
BIN=$(mktemp -d)/one_combat   # /mnt/project-files is noexec: run a hash-checked local copy
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "$SHA  $BIN" | sha256sum -c - || exit 1
export STS_EXECUTABLE_GIT_SHA=$EXEC_SHA
mkdir -p "$OUT"
for k in 0 1 2 3; do
  s=$((66000000 + 64*k))
  [ -e "$OUT/default$k.csv" ] && { echo "refusing to overwrite $OUT/default$k.csv" >&2; exit 1; }
  ( source $EV/env.sh
    { time taskset -c $k bash tools/seed_guard.sh "$BIN" bestbench 10000 64 0 $s "$OUT/default$k.csv" ; } \
      > "$OUT/default$k.log" 2>&1
    echo "exit $?" >> "$OUT/default$k.log" ) &
done
wait
echo "sources done" > "$OUT/DONE"
