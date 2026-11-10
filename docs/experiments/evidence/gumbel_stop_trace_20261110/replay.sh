#!/usr/bin/env bash
# Record of the smoke run (paths are the smoke container's scratchpad; tars from /mnt/project-files/gumbel-wholerun/units).
# replay.sh ARM SEED MODE(off|on)
set -uo pipefail
S=/tmp/claude-0/-home-user/e50bffde-c1e2-5ae3-af2e-003bcb840d39/scratchpad
ARM=$1 SEED=$2 MODE=$3
case $ARM in D) SIMS=10000;; *) SIMS=${ARM#G}000;; esac
u=$S/u/out/units/${SEED}_low
o=$S/rep/out; mkdir -p "$o"; tag=$ARM-$SEED-$MODE
mapfile -t E < <(grep '^STS_' "$u/$ARM-$SEED.env" | sed "s#^STS_OOC_HEART1=.*#STS_OOC_HEART1=$S/rep/net-0420.bin#")
E+=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE)
[ "$MODE" = on ] && { rm -f "$o/$tag.csv"; E+=("STS_SILVER_GUMBEL_STOP_TRACE=$o/$tag.csv"); }
cd /home/user/sts_ai || exit 2
t0=$(date +%s)
env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$S/rep/bin/one_combat" bestbench "$SIMS" 1 20 "$SEED" > "$o/$tag.log" 2> "$o/$tag.err"
echo "tag=$tag rc=$? wall=$(( $(date +%s) - t0 ))" > "$o/$tag.done"
