#!/usr/bin/env bash
cd /tmp/claude-0/gbm446
source /home/user/sts_ai/docs/experiments/evidence/silver_learned_stop/live_env.sh
export STS_SILVER_LEARNED_STOP=1 STS_STOP_AFTER_ACT=3
ARM=$1; export OMP_NUM_THREADS=2
if [ "$ARM" = T ]; then export STS_OOC_GBM_RANKER=$PWD/ooc_gbm_ranker_a20_sbl.txt STS_OOC_GBM_RANKER_DUMP=$PWD/dump8-T.csv; fi
bash /home/user/sts_ai/tools/seed_guard.sh ./one_combat bestbench 10000 8 20 79009001 smoke8-$ARM.csv > smoke8-$ARM.log 2>&1
echo rc=$? >> smoke8-$ARM.log
