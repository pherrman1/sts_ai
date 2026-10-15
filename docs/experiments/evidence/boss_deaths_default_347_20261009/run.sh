#!/usr/bin/env bash
# Stage 2 (PLAN.md): one bossrescue347 process per selected boss death, four
# workers, one CPU each, all under the default-stack environment.
# Usage: run.sh BINARY BINARY_SHA256 EXEC_GIT_SHA OUT SELECTION.json [STATE_ID...]
#   (from the frozen plan commit; no STATE_ID = every selected state)
set -u
SRC=$1 SHA=$2 EXEC_SHA=$3 OUT=$4 SEL=$5; shift 5
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
cd "$(git rev-parse --show-toplevel)"
EV=docs/experiments/evidence/boss_deaths_default_347_20261009
BIN=$(mktemp -d)/one_combat
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "$SHA  $BIN" | sha256sum -c - || exit 1
export STS_EXECUTABLE_GIT_SHA=$EXEC_SHA
mkdir -p "$OUT"
IDS=("$@")
[ ${#IDS[@]} -eq 0 ] && mapfile -t IDS < <(python3 -c "import json,sys; [print(e['stateId']) for e in json.load(open(sys.argv[1]))['selected']]" "$SEL")
run_entry() {   # run_entry STATE_ID CPU
  ( source $EV/env.sh
    { time taskset -c "$2" bash tools/seed_guard.sh "$BIN" bossrescue347 1 "$SEL" "$1" "$OUT/$1" ; } > "$OUT/$1.log" 2>&1
    echo "exit $?" >> "$OUT/$1.log" )
}
for k in 0 1 2 3; do
  ( for ((i = k; i < ${#IDS[@]}; i += 4)); do run_entry "${IDS[$i]}" "$k"; done ) &
done
wait
echo "run done" > "$OUT/DONE"
