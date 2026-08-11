#!/usr/bin/env bash
# Auto-restarting datagen: appends disjoint seed blocks onto vtrain_big.csv.
# A bad-seed assert (Monster::heal) aborts the process; abort() can't be caught,
# so instead we run in blocks and just advance past a crashed block. Each block's
# seeds are disjoint (STEP == BLOCK) so no run is ever duplicated in the CSV.
set -u
OUT=build/vtrain_big.csv
LOG=build/vtrain_big.log
SIMS=2500
ASC=0
EPS=0.3
BLOCK=50000
OFF=${1:-200000}          # start offset (must be > any seed already in OUT)
END=${2:-3000000}         # stop after this offset
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-12}

echo "=== datagen_loop start $(date) off=$OFF end=$END block=$BLOCK sims=$SIMS ===" >>"$LOG"
while [ "$OFF" -lt "$END" ]; do
    ./one_combat.elf datagen "$BLOCK" "$SIMS" "$ASC" "$EPS" "$OUT" 0 "$OFF" >>"$LOG" 2>&1
    rc=$?
    echo "=== block off=$OFF exited rc=$rc rows=$(wc -l <"$OUT") $(date) ===" >>"$LOG"
    OFF=$((OFF + BLOCK))
done
echo "=== datagen_loop done $(date) ===" >>"$LOG"
