#!/bin/bash
# usage: VA4_DATA=DIR run_all.sh   (DIR holds a4.pkl, run1_a4.pkl from #911 and more_a4.pkl, states_a4.pkl from extract_*; see README)
set -e; cd "$(dirname "$0")"; L=../logs; mkdir -p $L
for s in exp1 exp2 exp3 exp4 exp5; do python $s.py 2>&1 | grep -v Warn > $L/$s.log; done
python exp3.py 1 2>&1 | grep -v Warn > $L/exp3_extra.log
python build_aug.py > $L/build_aug.log 2>&1
python exp6.py 2>&1 | grep -v Warn > $L/exp6.log
python exp8_counters.py 2>&1 | grep -v Warn > $L/exp8_counters.log
python exp7_attn.py all 32 1 2>&1 | grep -v Warn > $L/exp7_attn.log
python cmp_g.py 2>&1 | grep -v Warn > $L/cmp_g.log
python oldtest_check.py 2>&1 | grep -v Warn > $L/oldtest_check.log
python fit_va4.py > $L/fit_va4.log 2>&1
