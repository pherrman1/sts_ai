#!/usr/bin/env bash
# V0: leafbench on the split-0 D2 roots, 4 lanes. usage: run_v0.sh SCRATCH
set -uo pipefail
S=$1
cd /home/user/sts_ai
source docs/experiments/evidence/gumbel_distill_d2_20261110/record_env.sh
for k in 0 1 2 3; do
  ( zcat $S/v0/rows*.jsonl.gz | awk -v k=$k 'NR%5==0 && (NR/5)%4==k' | env -i PATH=/usr/bin:/bin HOME=$HOME "${D2_ENV[@]}" \
      $S/one_combat_lb leafbench $S/v0/lb$k.jsonl 256 8 $S/n_f1.ctn \
      > $S/v0/lb$k.log 2>&1; echo "rc=$?" >> $S/v0/lb$k.log ) &
done
wait
