#!/usr/bin/env bash
# #367 pilot: 128 paired seeds 49000001..49000128, 4 shards x 32 seeds; each shard runs control then vwin.
set -u
cd /home/user/sts_ai
BIN=/tmp/claude-0/pilot/one_combat-b6710750
P=/mnt/project-files/silver-vwin-leaf-367/pilot
export STS_SILVER_LEARNED_STOP=1
for i in 0 1 2 3; do
  (
    lo=$((49000001 + 32*i))
    tools/seed_guard.sh $BIN bestbench 10000 32 0 $lo $P/control$i.csv > $P/control$i.log 2>&1
    STS_SILVER_VWIN_LEAF=1 STS_SILVER_VWIN_LEAF_SAMPLES=4 tools/seed_guard.sh $BIN bestbench 10000 32 0 $lo $P/vwin$i.csv > $P/vwin$i.log 2>&1
    echo "shard $i done $(date -u +%FT%TZ)" >> $P/DONE
  ) &
done
wait
echo "all done $(date -u +%FT%TZ)" >> $P/DONE
