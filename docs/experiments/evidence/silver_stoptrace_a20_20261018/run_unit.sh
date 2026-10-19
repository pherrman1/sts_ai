#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT T SEED -- one guarded one-seed A20 bestbench full run with the Silver stop
# trace on (2 h timeout: rc 124); always exits 0 (rc is in the .done line).
# Configuration (PLAN.md) = the §538 F10 arm (flat exact 10k; student_sel policyStep out of combat; gen-7f MLP as
# rollout root table and root/tree prior, weight 400, K=8; STS_ACTIVE_POWER_FEATURES=1) plus
# STS_SILVER_STOP_TRACE, which runs every checkpoint 250..10k of each multi-action root and writes features + leader.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 SEED=$5
[ "$ARM" = T ] || { echo "unknown arm $ARM" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
PRIOR=models/combat_policy_mlp_g7f_E.txt
mkdir -p "$OUT"; base=$OUT/$ARM-$SEED
rm -f "$base.trace.csv"   # the trace appends; a rerun of the unit starts it fresh
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 STS_ACTIVE_POWER_FEATURES=1
  "STS_SILVER_ROLLOUT_ROOT_TABLE=$PRIOR" "STS_SILVER_ROOT_PRIOR=$PRIOR"
  STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  "STS_SILVER_STOP_TRACE=$base.trace.csv"
  "STS_OOC_HEART1=$RUN/student_sel.bin" STS_OOC_CPU_PROFILE=1 "STS_OOC_DECISION_TRACE=$base.ooc.jsonl")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 20 "$SEED" "$base.csv" > "$base.log" 2> "$base.err"
rc=$?
[ "$rc" = 0 ] && ! grep -q "rollout root table model loaded: $PRIOR" "$base.err" "$base.log" && rc=97
[ "$rc" = 0 ] && [ ! -s "$base.trace.csv" ] && rc=98
[ -f "$base.trace.csv" ] && gzip -f "$base.trace.csv"
echo "tag=$ARM-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
