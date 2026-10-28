#!/usr/bin/env bash
# trace-check every finished replay against its §683 MAP source; prints one line per seed.
for d in /tmp/claude-0/-home-user-sts-ai/2b679114-f863-50d0-b6c9-a07cf05118e7/scratchpad/cp/run-38bd5a71/out/P-*.done; do
  s=$(basename $d .done); s=${s#P-}
  src=/tmp/claude-0/-home-user-sts-ai/2b679114-f863-50d0-b6c9-a07cf05118e7/scratchpad/src/MAP-$s.jsonl.gz
  if [ ! -f $src ]; then t=$(ls /mnt/project-files/ooc-map-only-search/units/$s.w*.tar); tar -xOf $t out/units/$s/MAP-$s.jsonl.gz > $src; fi
  echo "$s $(python3 /home/user/sts_ai/docs/experiments/evidence/campfire_price_stage0_20261026/trace_check.py --prefix /tmp/claude-0/-home-user-sts-ai/2b679114-f863-50d0-b6c9-a07cf05118e7/scratchpad/cp/run-38bd5a71/out/P-$s.jsonl $src)"
done
