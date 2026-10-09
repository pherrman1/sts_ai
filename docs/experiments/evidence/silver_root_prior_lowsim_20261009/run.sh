#!/bin/bash
cd /home/user/sts_ai
export OMP_NUM_THREADS=4 STS_SILVER_EXACT_ROOT_BUDGETS=1
B=/home/user/synth/one_combat_screen; O=/home/user/lowsim; P=/mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/prior-natpert.compact.txt
s=$(date +%s); tools/seed_guard.sh $B bestbench 256 32 0 61000000 $O/A-plain256.csv > $O/A.log 2>&1; echo A $(( $(date +%s)-s )) >> $O/wall.txt
s=$(date +%s); STS_SILVER_ROOT_PRIOR=$P STS_SILVER_ROOT_PRIOR_WEIGHT=400 tools/seed_guard.sh $B bestbench 256 32 0 61000000 $O/B-prior256.csv > $O/B.log 2>&1; echo B $(( $(date +%s)-s )) >> $O/wall.txt
s=$(date +%s); tools/seed_guard.sh $B bestbench 2000 32 0 61000000 $O/C-plain2k.csv > $O/C.log 2>&1; echo C $(( $(date +%s)-s )) >> $O/wall.txt
echo FINISHED > $O/done.txt
