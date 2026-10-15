#!/bin/bash
cd /home/user/sts_ai
export OMP_NUM_THREADS=4 STS_SILVER_EXACT_ROOT_BUDGETS=1
B=/home/user/synth/one_combat_screen; O=/home/user/lowsim; P=/mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/prior-natpert.compact.txt
for S in 512 1000 2000 4000; do
s=$(date +%s); STS_SILVER_ROOT_PRIOR=$P STS_SILVER_ROOT_PRIOR_WEIGHT=400 tools/seed_guard.sh $B bestbench $S 128 0 61001000 $O/c128-prior$S.csv > $O/c128-prior$S.log 2>&1; echo prior$S $(( $(date +%s)-s )) >> $O/c128-wall.txt
done
s=$(date +%s); tools/seed_guard.sh $B bestbench 10000 128 0 61001000 $O/c128-plain10k.csv > $O/c128-plain10k.log 2>&1; echo plain10k $(( $(date +%s)-s )) >> $O/c128-wall.txt
echo FINISHED > $O/sweep-done.txt
