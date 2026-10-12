#!/usr/bin/env bash
# usage: run.sh BIN ARM LO N OUTBASE [wrapper...]
TIMEFORMAT="real %R user %U sys %S"
set -uo pipefail
BIN=$1 ARM=$2 LO=$3 N=$4 base=$5; shift 5
REPO=/home/user/sts_ai
RUN=$(mktemp -d); git -C $REPO rev-parse HEAD > $RUN/GITSHA
source $REPO/docs/experiments/evidence/ooc_rollout3_replication_20261010/arm_env.sh
mapfile -t E < <(arm_env_args "$ARM" "$base" "$RUN")
cd $REPO
{ time env -i "${E[@]}" ${EXTRA_ENV:-} bash tools/seed_guard.sh "$@" "$BIN" bestbench 10000 "$N" 0 "$LO" "$base.csv" > "$base.log" 2> "$base.err"; } 2> "$base.time"
echo "rc=$?" >> "$base.log"
