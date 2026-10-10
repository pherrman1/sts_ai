#!/usr/bin/env bash
cd /home/user/sts_ai
S=/tmp/claude-0/smoke
for k in 0 1 2 3; do
  ( source docs/experiments/evidence/boss_deaths_default_347_20261009/env.sh
    taskset -c $k bash tools/seed_guard.sh build/linux-gcc-release/one_combat bestbench 10000 4 0 $((66009000+4*k)) $S/smoke$k.csv > $S/smoke$k.log 2>&1 ) &
done
wait
