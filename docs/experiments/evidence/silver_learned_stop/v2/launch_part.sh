#!/usr/bin/env bash
# Parallel split of the frozen v2 confirmation (PLAN.md): same binary, same seeds,
# the plan's ranges divided into 4 disjoint parts of 32 replay + 32 live seeds.
#   part M (0..3): replay seeds 44000000+32M .. +31, live seeds 45000000+32M .. +31,
#   4 shards of 8 seeds per part, one CPU each.
# Usage: launch_part.sh M [BINARY_SOURCE] [OUT]   (run from a checkout of the plan commit)
set -u
M=$1
SRC=${2:-/mnt/project-files/silver-learned-stop/one_combat-adbcae75}
OUT=${3:-/mnt/project-files/silver-learned-stop/run2/part$M}
cd "$(git rev-parse --show-toplevel)"
EV=docs/experiments/evidence/silver_learned_stop
mkdir -p "$OUT"
# The shared folder is not executable: run a local copy, checked by hash.
BIN=$(mktemp -d)/one_combat
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "8e5e733d5ce48db5f8dd41b6b0c59aaa27509fb1e75c19212c4b88e21a3258c9  $BIN" | sha256sum -c - || exit 1
"$BIN" >/dev/null 2>&1; [ $? -ne 126 ] || { echo "binary not executable"; exit 1; }
export STS_EXECUTABLE_GIT_SHA=adbcae7520229b9b280487db45497ae3b2c17d8e
for k in 0 1 2 3; do
  rs=$((44000000 + 32*M + 8*k)); ls=$((45000000 + 32*M + 8*k))
  (
    ( source $EV/replay_env.sh
      { time taskset -c $k bash tools/seed_guard.sh $BIN silverstopreplaygen 8 10000 0 \
          $OUT/replay$k $rs $EV/v2/teacher.json ; } > $OUT/replay$k.log 2>&1
      echo "exit $?" >> $OUT/replay$k.log )
    ( source $EV/live_env.sh; export STS_SILVER_ADAPTIVE=1
      { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 8 0 \
          $ls $OUT/live_control$k.csv ; } > $OUT/live_control$k.log 2>&1
      echo "exit $?" >> $OUT/live_control$k.log )
    ( source $EV/live_env.sh; export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1
      { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 8 0 \
          $ls $OUT/live_learned$k.csv ; } > $OUT/live_learned$k.log 2>&1
      echo "exit $?" >> $OUT/live_learned$k.log )
  ) &
done
wait
echo "part $M done" > "$OUT/DONE"
