#!/usr/bin/env bash
# Resumable N=128 run: reruns every seed without a .done.
R=$SCRATCH/run-n128
for s in $(cat $R/seeds.txt); do
  [ -f $R/out/P-$s.done ] && continue
  rm -f $R/out/P-$s.*
  echo $s
done > $R/todo.txt
echo "todo $(wc -l < $R/todo.txt) $(date -u +%FT%TZ)"
cat $R/todo.txt | STOP_AT_ACT4=1 xargs -P 4 -I{} /home/user/sts_ai/docs/experiments/evidence/campfire_price_stage0_20261026/replay_unit.sh /home/user/wt-38bd $R $R/out {} 128
echo "done $(ls $R/out/*.done | wc -l) $(date -u +%FT%TZ)"
