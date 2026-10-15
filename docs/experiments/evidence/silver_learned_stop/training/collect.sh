#!/usr/bin/env bash
# Learned-stop training data: exact-checkpoint trace, seeds 41000000..41000031, 4 shards x 8.
set -u
cd /home/user/sts_ai
source /tmp/claude-0/ls/env.sh   # committed as training/env.sh (identical to live_env.sh)
export STS_EXECUTABLE_GIT_SHA=78347c7ea7b10f929f07f08110181c6de799ffd3
OUT=/tmp/claude-0/ls/collect
for k in 0 1 2 3; do
  start=$((41000000 + 8*k))
  ( { time STS_SILVER_STOP_TRACE=$OUT/shard$k.trace.csv taskset -c $k bash tools/seed_guard.sh \
      /tmp/claude-0/ls/frozen-78347c7e/one_combat bestbench 10000 8 0 $start $OUT/shard$k.results.csv ; } \
      > $OUT/shard$k.log 2>&1; echo "exit $?" >> $OUT/shard$k.log ) &
done
wait
