#!/usr/bin/env bash
# More learned-stop training traces: seeds 41000032..41000159, 4 shards x 32. Binary ae7a6d79.
set -u
cd /home/user/sts_ai
BIN=/tmp/claude-0/ls/frozen-ae7a6d79/one_combat
echo "2136c77015a1546d9b538bd9603dcee377dd468b6a9f71f3b21e0b875aefa119  $BIN" | sha256sum -c - || exit 1
source docs/experiments/evidence/silver_learned_stop/training/env.sh
export STS_EXECUTABLE_GIT_SHA=ae7a6d79ed6b98963d6d5467686dcaec4815ef62
OUT=/tmp/claude-0/ls/collect2
for k in 0 1 2 3; do
  start=$((41000032 + 32*k))
  ( { time STS_SILVER_STOP_TRACE=$OUT/shard$k.trace.csv taskset -c $k bash tools/seed_guard.sh \
      $BIN bestbench 10000 32 0 $start $OUT/shard$k.results.csv ; } \
      > $OUT/shard$k.log 2>&1; echo "exit $?" >> $OUT/shard$k.log ) &
done
wait
