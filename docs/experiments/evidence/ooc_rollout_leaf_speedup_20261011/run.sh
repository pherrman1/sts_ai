#!/usr/bin/env bash
# usage: run.sh BINDIR ARM SEED OUTBASE [extra KEY=VAL...]
# One guarded one-seed bestbench unit with the §422 arm environment (ARM = rollout3 | off).
# BINDIR holds one_combat and GITSHA. Extra KEY=VAL pairs (e.g. STS_OOC_CPU_PROFILE=1) are appended.
set -uo pipefail
BIN=$1 ARM=$2 SEED=$3 base=$4; shift 4
REPO=$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)
source "$REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh"
mapfile -t E < <(arm_env_args "$ARM" "$base" "$BIN")
cd "$REPO"
t0=$(date +%s.%N)
env -i "${E[@]}" "$@" bash tools/seed_guard.sh "$BIN/one_combat" bestbench 10000 1 0 "$SEED" "$base.csv" > "$base.log" 2> "$base.err"
rc=$?; echo "rc=$rc wall=$(echo "$(date +%s.%N) - $t0" | bc)" >> "$base.err"
