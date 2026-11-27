#!/bin/bash
# Starts w5_eval.py once the side job (one_combat expertfights) is gone and MemAvailable >= 3 GB; retries after a
# memguard abort (exit 3) up to 6 times, always waiting for the same condition first.
cd "$(dirname "$0")"
for try in 1 2 3 4 5 6; do
  while pgrep -x one_combat >/dev/null || [ "$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)" -lt 3000 ]; do sleep 60; done
  echo "$(date '+%F %T') start try $try" >> run_w5.log
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 ionice -c3 python3 -E w5_eval.py ~/Documents/sts/ds_repo . 2 > eval.log 2>&1
  rc=$?; echo "$(date '+%F %T') exit $rc" >> run_w5.log
  [ $rc -ne 3 ] && break
  sleep 600
done
