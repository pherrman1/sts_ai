#!/bin/bash
# Phase F (5.7.2) paired A/B: distilled-policy gate arms on the recorded
# 128-seed fair block (seeds 126700-126827, 1000 sims, 12 threads). The six
# gates are ON (no MAP gate), score source = policy (sigmoid of the policy
# logit, STS_OOC_STRATEGIC_SCORE=policy), margins in probability points.
# Compared against the §96 Q-gate arms (build/qwin_cal_m*.csv) and the V3
# reference (build/gates_ref_m1.csv, 39.8%).
set -u
cd /home/philippherrmann/Documents/sts/sts_lightspeed
export STS_FAIR=1 OMP_NUM_THREADS=12
export STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
export STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
export STS_OOC_STRATEGIC_SCORE=policy
for l in 025 050; do
  for m in 0.01 0.03 0.05 0.10; do
    echo "=== dist_l$l m$m ==="
    STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic_qwin_cal_dist_l${l}.native \
    STS_OOC_STRATEGIC_MARGIN=$m \
    ./build/one_combat bestbench 1000 128 0 126700 build/qwin_cal_dist_l${l}_m${m}.csv \
      > build/qwin_cal_dist_l${l}_m${m}.log 2>&1
    grep 'BEST  ' build/qwin_cal_dist_l${l}_m${m}.log
  done
done
echo ALL_DIST_GATES_DONE
