#!/usr/bin/env bash
# Auto-restarting RICH datagen (datagen2): appends disjoint seed blocks onto
# build/vrich.csv. A bad-seed assert (e.g. Monster::heal) aborts the process and
# abort() can't be caught, so we run in blocks and just advance past a crashed
# block. Each block's seeds are disjoint so no run is ever duplicated.
# Uses the CURRENT BEST play policy (server cards skip@0 + shop-V), so it needs
# v_server.py — this script starts it if it isn't already listening on :5555.
set -u
OUT=${OUT:-build/vrich.csv}
LOG=${LOG:-build/vrich.log}
SIMS=${SIMS:-1000}
# datagen2 exploration: card picks are softmax-sampled by V-marginal (temp
# STS_DG_TEMP, default 3.0); EPS below is the UNIFORM-floor prob (coverage of
# V's blind spots), not the old eps-greedy random rate.

# --- ensure the value server is up (best-policy datagen queries it) ---
if ! python3 -c "import socket,sys; s=socket.socket(); s.settimeout(1);
sys.exit(0 if s.connect_ex(('127.0.0.1',5555))==0 else 1)" 2>/dev/null; then
    echo "=== starting v_server.py $(date) ===" >>"$LOG"
    ( cd "$(dirname "$0")/../.." && python3 v_server.py >>"$LOG" 2>&1 ) &
    for _ in $(seq 1 20); do
        python3 -c "import socket,sys; s=socket.socket(); s.settimeout(1);
sys.exit(0 if s.connect_ex(('127.0.0.1',5555))==0 else 1)" 2>/dev/null && break
        sleep 1
    done
fi
ASC=${ASC:-0}
EPS=${EPS:-0.05}          # uniform-floor prob (see note above); softmax handles the rest
BLOCK=${BLOCK:-50000}
OFF=${1:-0}               # start seed offset (must exceed any seed already in OUT)
END=${2:-300000}          # stop after this offset
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-12}

echo "=== datagen2_loop start $(date) off=$OFF end=$END block=$BLOCK sims=$SIMS ===" >>"$LOG"
while [ "$OFF" -lt "$END" ]; do
    # datagen2 args: nSeeds sims asc eps out seedOffset
    ./one_combat.elf datagen2 "$BLOCK" "$SIMS" "$ASC" "$EPS" "$OUT" "$OFF" >>"$LOG" 2>&1
    rc=$?
    echo "=== block off=$OFF exited rc=$rc rows=$(wc -l <"$OUT" 2>/dev/null) $(date) ===" >>"$LOG"
    OFF=$((OFF + BLOCK))
done
echo "=== datagen2_loop done $(date) rows=$(wc -l <"$OUT" 2>/dev/null) ===" >>"$LOG"
