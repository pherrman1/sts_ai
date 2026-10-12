#!/usr/bin/env bash
cd /tmp/claude-0/gbm447
source /home/user/sts_ai/docs/experiments/evidence/silver_learned_stop/live_env.sh
export STS_SILVER_LEARNED_STOP=1 STS_STOP_AFTER_ACT=3 OMP_NUM_THREADS=2 STS_EXECUTABLE_GIT_SHA=5cb1e86d893560a03b664af3991d68bb069de226
ARM=$1
if [ "$ARM" = T ]; then export STS_OOC_GBM_RANKER=$PWD/ooc_gbm_ranker_a20_sbl.txt; fi
bash /home/user/sts_ai/tools/seed_guard.sh ./one_combat bestbench 10000 128 20 79000000 $ARM.csv > $ARM.log 2>&1
echo rc=$? >> $ARM.log
