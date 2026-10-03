#!/usr/bin/env bash
# Frozen learned-stop A/B (see PLAN.md). Code ae7a6d79, binary sha256 2136c770...a119.
# Part A: replay A/B, seeds 42000000..42000095, 4 shards x 24.
# Part B: live paired runs, seeds 43000000..43000127, 4 shards x 32, control then treatment per core.
set -u
cd /home/user/sts_ai
BIN=/tmp/claude-0/ls/frozen-ae7a6d79/one_combat
EV=docs/experiments/evidence/silver_learned_stop
OUT=/tmp/claude-0/ls/run
mkdir -p $OUT
export STS_EXECUTABLE_GIT_SHA=ae7a6d79ed6b98963d6d5467686dcaec4815ef62
for k in 0 1 2 3; do
  (
    ( source $EV/replay_env.sh
      { time taskset -c $k bash tools/seed_guard.sh $BIN silverstopreplaygen 24 10000 0 \
          $OUT/replay$k $((42000000 + 24*k)) $EV/teacher.json ; } > $OUT/replay$k.log 2>&1
      echo "exit $?" >> $OUT/replay$k.log )
    ( source $EV/live_env.sh; export STS_SILVER_ADAPTIVE=1
      { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 32 0 \
          $((43000000 + 32*k)) $OUT/live_control$k.csv ; } > $OUT/live_control$k.log 2>&1
      echo "exit $?" >> $OUT/live_control$k.log )
    ( source $EV/live_env.sh; export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1
      { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 32 0 \
          $((43000000 + 32*k)) $OUT/live_learned$k.csv ; } > $OUT/live_learned$k.log 2>&1
      echo "exit $?" >> $OUT/live_learned$k.log )
  ) &
done
wait
