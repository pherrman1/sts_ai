#!/bin/bash
# 5.3.2 map-DAG A/B on the recorded 128-seed fair block (seeds 126700-126827,
# 1000 sims, 12 threads): V5 base (no encoder) vs V6 (E1 frozen-base encoder),
# MAP gate on at probability-point margins, other six gates on in both arms.
# Reference: build/gates_ref_m1.csv (39.8%, V3 legacy m1.0).
set -u
cd /home/philippherrmann/Documents/sts/sts_lightspeed
export STS_FAIR=1 OMP_NUM_THREADS=12
export STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
export STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MAP=1
for model in qwin_cal map_enc; do
  for m in 0.01 0.03 0.05 0.10; do
    echo "=== $model m$m ==="
    STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic_${model}.native \
    STS_OOC_STRATEGIC_MARGIN=$m \
    ./build/one_combat bestbench 1000 128 0 126700 build/mapgate_${model}_m${m}.csv \
      > build/mapgate_${model}_m${m}.log 2>&1
    grep 'BEST  ' build/mapgate_${model}_m${m}.log
  done
done
echo ALL_DONE
