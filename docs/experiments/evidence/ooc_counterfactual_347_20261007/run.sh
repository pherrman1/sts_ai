#!/usr/bin/env bash
# #347 OOC counterfactual (PLAN.md): one bossrescue347 process per selected
# source, at most four workers, one CPU each, under the #417 mcts arm
# environment plus the spec's STS_347_* flags and the OOC decision trace.
# Usage: run.sh BINARY BINARY_SHA256 EXEC_GIT_SHA OUT SELECTION.json [STATE_ID...]
set -u
SRC=$1 SHA=$2 EXEC_SHA=$3 OUT=$4 SEL=$5; shift 5
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
export STS_EXECUTABLE_GIT_SHA=$EXEC_SHA
mkdir -p "$OUT"
IDS=("$@")
[ ${#IDS[@]} -eq 0 ] && mapfile -t IDS < <(python3 -c "import json,sys; [print(e['stateId']) for e in json.load(open(sys.argv[1]))['selected']]" "$SEL")
field() { python3 -c "import json,sys; e=[e for e in json.load(open(sys.argv[1]))['selected'] if e['stateId']==sys.argv[2]][0]; v=e.get(sys.argv[3]); print(int(v) if isinstance(v,bool) else v)" "$SEL" "$1" "$2"; }
run_entry() {   # run_entry STATE_ID CPU
  local arm chest camp
  arm=$(field "$1" sourceArm) && chest=$(field "$1" chestRule) && camp=$(field "$1" campfireChain) || return 1
  ( source "$TMP/arm_env.sh" && arm_env "$arm" || exit 1
    export STS_OOC_DECISION_TRACE="$OUT/$1.ooc.jsonl"
    [ "$chest" = 1 ] && export STS_347_CHEST_RULE=1
    [ "$camp" = 1 ] && export STS_347_CAMPFIRE_CHAIN=1
    { time taskset -c "$2" bash tools/seed_guard.sh "$BIN" bossrescue347 1 "$SEL" "$1" "$OUT/$1" ; } > "$OUT/$1.log" 2>&1
    echo "exit $?" >> "$OUT/$1.log" )
}
for k in 0 1 2 3; do
  ( for ((i = k; i < ${#IDS[@]}; i += 4)); do run_entry "${IDS[$i]}" "$k"; done ) &
done
wait
echo "run done" > "$OUT/DONE"
