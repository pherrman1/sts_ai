#!/usr/bin/env bash
# X4 (WORKPLAN-3): after today's 15:00 bench: snapshot run -> split -> 128 arm -> 1024 arm (stop at 20:50)
D=~/Documents/sts/stage1/amber_combat_gap_20261127; X=$D/x4; LOG=$X/chain.log
R=~/Documents/sts/fightlog_repo; MOD=$X/module; CK=~/Documents/sts/stage1/amber_scratch/ckpt_1828683.pt
F=$(cat $D/smoke/flags_common.txt)
GPU="--packed-h2d --fused-layer --gpu-timing"
other() { pgrep -f 'selfplay.py.*--min-replay' | while read p; do grep -q amber_combat_gap /proc/$p/cmdline 2>/dev/null || echo $p; done | head -1; }
log() { echo "$(date '+%F %T') $*" >> $LOG; }
memwatch() {   # kill $1 if MemAvailable < 1000 MB or a periodic bench starts
  while kill -0 $1 2>/dev/null; do
    A=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    if [ "$A" -lt 1000 ]; then log "memwatch kill $1 MemAvailable=$A"; kill $1; fi
    if [ -n "$(other)" ]; then log "bench started, stop $1"; kill $1; fi
    if [ "$(date +%H%M)" -ge 2050 ]; then log "20:50 window end, stop $1"; kill $1; fi
    sleep 5
  done
}
log "chain start, waiting for the 15:00 bench to finish"
until [ "$(date +%H%M)" -ge 1500 ]; do sleep 30; done
seen=0; quiet=0
while true; do
  if [ -n "$(other)" ]; then seen=1; quiet=0; else quiet=$((quiet+1)); fi
  if [ $seen = 1 ] && [ $quiet -ge 6 ]; then break; fi
  if [ $seen = 0 ] && [ "$(date +%H%M)" -ge 1545 ]; then log "no bench seen by 15:45, starting"; break; fi
  sleep 30
done
log "bench done; snapshot run"
cd $R
run() {   # out extra-args...
  local out=$1; shift; mkdir -p $out
  nice -n 10 tools/seed_guard.sh python3 tools/az_bench/selfplay.py --module-dir $MOD --device cuda --out-dir $out --init-net $CK \
    --ascension 20 $F $GPU "$@" > $out/out.log 2>&1 &
  local p=$!; memwatch $p; wait $p; local rc=$?; log "$(basename $out) rc=$rc"; return $rc
}
run $X/snap --seed-base 160200000 --max-runs 1000 --workers 3 --games 40 --fight-dump $X/dump --fight-dump-copies 4 --death-log $X/snap/deaths.jsonl || { log "snapshot run failed"; exit 1; }
sha256sum $X/dump/*.states | sha256sum > $X/dump.sha256; python3 $X/filter.py $X >> $LOG 2>&1
run $X/a128 --seed-base 160300000 --max-runs 1000000 --workers 3 --games 40 --fight-roots "$(cat $X/files128.txt)" --fight-log $X/a128/fights.jsonl
[ "$(date +%H%M)" -lt 2045 ] || { log "no time for 1024"; exit 0; }
F=$(echo "$F" | sed 's/--fast-sims 128/--fast-sims 1024/')
run $X/a1024 --seed-base 160300000 --max-runs 1000000 --workers 3 --games 40 --fight-roots "$(cat $X/files1024.txt)" --fight-log $X/a1024/fights.jsonl
log CHAIN_DONE
