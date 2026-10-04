#!/usr/bin/env bash
# Frozen learned-stop v2 confirmation (see PLAN.md). Code adbcae75, binary sha256 8e5e733d...58c9.
# Part A: replay A/B (control, adaptive199, lockonly, learned), seeds 44000000..44000127, 4 shards x 32.
# Part B: live paired runs, seeds 45000000..45000127, 4 shards x 32, control then learned per core.
set -u
cd /home/user/sts_ai
BIN=/tmp/claude-0/ls/frozen-adbcae75/one_combat
EV=docs/experiments/evidence/silver_learned_stop
OUT=/tmp/claude-0/ls/run2
mkdir -p $OUT
echo "8e5e733d5ce48db5f8dd41b6b0c59aaa27509fb1e75c19212c4b88e21a3258c9  $BIN" | sha256sum -c - || exit 1
export STS_EXECUTABLE_GIT_SHA=adbcae7520229b9b280487db45497ae3b2c17d8e
for k in 0 1 2 3; do
  (
    ( source $EV/replay_env.sh
      { time taskset -c $k bash tools/seed_guard.sh $BIN silverstopreplaygen 32 10000 0 \
          $OUT/replay$k $((44000000 + 32*k)) $EV/v2/teacher.json ; } > $OUT/replay$k.log 2>&1
      echo "exit $?" >> $OUT/replay$k.log )
    ( source $EV/live_env.sh; export STS_SILVER_ADAPTIVE=1
      { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 32 0 \
          $((45000000 + 32*k)) $OUT/live_control$k.csv ; } > $OUT/live_control$k.log 2>&1
      echo "exit $?" >> $OUT/live_control$k.log )
    ( source $EV/live_env.sh; export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1
      { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 32 0 \
          $((45000000 + 32*k)) $OUT/live_learned$k.csv ; } > $OUT/live_learned$k.log 2>&1
      echo "exit $?" >> $OUT/live_learned$k.log )
  ) &
done
wait
