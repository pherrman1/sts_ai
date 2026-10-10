#!/usr/bin/env bash
cd /home/user/sts_ai
S=/tmp/claude-0/smoke
k=0
for id in smoke-66009003-a3 smoke-66009011-a3 smoke-66009015-a2; do
  ( source docs/experiments/evidence/boss_deaths_default_347_20261009/env.sh
    { time taskset -c $k bash tools/seed_guard.sh build/linux-gcc-release/one_combat bossrescue347 1 $S/smoke_selection.json $id $S/$id ; } > $S/$id.log 2>&1
    echo "exit $?" >> $S/$id.log ) &
  k=$((k+1))
done
wait
