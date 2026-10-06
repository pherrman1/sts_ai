#!/usr/bin/env bash
# #367 diagnosis: replay pilot control seeds 49000001..49000016 with the audit hook only (play unchanged).
cd /home/user/sts_ai
BIN=/tmp/claude-0/pilot/one_combat-audit
D=/mnt/project-files/silver-vwin-leaf-367/audit
export STS_SILVER_LEARNED_STOP=1
for i in 0 1 2 3; do
  lo=$((49000001 + 4*i))
  STS_SILVER_VWIN_LEAF_AUDIT=$D/audit$i.jsonl tools/seed_guard.sh $BIN bestbench 10000 4 0 $lo $D/control$i.csv > $D/control$i.log 2>&1 &
done
wait
echo done > $D/DONE
