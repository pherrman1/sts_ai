#!/usr/bin/env bash
# Frozen #400 Stage 1 cohort: seeds 40000000..40000127, 4 shards x 32 seeds.
set -u
cd /home/user/sts_ai
source /tmp/claude-0/sp400/env.sh
export STS_EXECUTABLE_GIT_SHA=31de6a6d96a752eacd2b919e58ea94d89fc8ff7e
OUT=/tmp/claude-0/sp400/run
mkdir -p $OUT
for k in 0 1 2 3; do
  start=$((40000000 + 32*k))
  ( { time taskset -c $k bash tools/seed_guard.sh /tmp/claude-0/sp400/frozen/one_combat silverparams400gen 32 10000 0 \
      $OUT/shard$k $start /tmp/claude-0/sp400/teacher.json ; } > $OUT/shard$k.log 2>&1; echo "exit $?" >> $OUT/shard$k.log ) &
done
wait
