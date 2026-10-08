#!/usr/bin/env bash
# #347 uniform-prior OOC MCTS pilot (PLAN.md): seeds 53000000..53000031 in four
# shards of 8, one CPU each, one arm: the #417 `mcts` arm with a uniform prior.
# Chest and relic rules and the keys-off filter are built in (no flag).
# Usage: launch.sh BINARY BINARY_SHA256 BUILD_GIT_SHA OUT   (absolute paths)
#        launch.sh BINARY BINARY_SHA256 BUILD_GIT_SHA OUT smoke   (seed 53009000, act 1 only)
set -u
SRC=$1 SHA=$2 BUILD_SHA=$3 OUT=$4 MODE=${5:-run}
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
cd "$(git rev-parse --show-toplevel)"
ARM_ENV_REF=10e56bd813202db969ddb176aad8ed33173179f7:docs/experiments/evidence/ooc_mcts_vs_off_pilot_20261006/arm_env.sh
ARM_ENV_SHA=cc0ec6aa1f22bdb537280fedc8992080c35f1a8d2acd4e975305e0f956c6cc97
TMP=$(mktemp -d)
git show "$ARM_ENV_REF" > "$TMP/arm_env.sh" || exit 1
echo "$ARM_ENV_SHA  $TMP/arm_env.sh" | sha256sum -c - || exit 1
BIN=$TMP/one_combat
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "$SHA  $BIN" | sha256sum -c - || exit 1
export STS_EXECUTABLE_GIT_SHA=$BUILD_SHA
mkdir -p "$OUT"
git rev-parse HEAD > "$OUT/PLAN_COMMIT"
run_shard() {   # run_shard CPU SEED_START COUNT TAG [STOP_ACT]
  ( source "$TMP/arm_env.sh" && arm_env mcts || exit 1
    export STS_OOC_MCTS_PRIOR=uniform STS_OOC_DECISION_TRACE="$OUT/uniform$4.ooc.jsonl"
    [ -n "${5:-}" ] && export STS_STOP_AFTER_ACT=$5
    for f in "$OUT/uniform$4.csv" "$OUT/uniform$4.ooc.jsonl"; do
      [ -e "$f" ] && { echo "refusing: stale $f" >&2; exit 1; }; done
    { time taskset -c "$1" bash tools/seed_guard.sh "$BIN" bestbench 10000 "$3" 0 \
        "$2" "$OUT/uniform$4.csv" ; } > "$OUT/uniform$4.log" 2>&1
    echo "exit $?" >> "$OUT/uniform$4.log" )
}
if [ "$MODE" = smoke ]; then
  run_shard 0 53009000 1 smoke 1; echo "smoke done" > "$OUT/SMOKE_DONE"; exit 0
fi
for k in 0 1 2 3; do run_shard "$k" $((53000000 + 8*k)) 8 "$k" & done
wait
echo "run done" > "$OUT/DONE"
