#!/usr/bin/env bash
# 3-source smoke of a leaf net in the fight-level A/B harness (../../silver_leaf_head_ab_20261022): sources
# 111339997-999 (the A/B's smoke sources, incl. the fights where the first heads failed), base10000 (production) vs
# head10000 (the net as leaf: blend BLEND, TP points per turn, win-now cap WINCAP), one_combat 83de6c12... (the A/B's
# binary). Three sources at once; about 20-55 minutes on 4 cores.
# usage (repo root): W=WORKDIR [BLEND=0.5] [TP=1] run_smoke.sh TAG HEAD TRUNK WINCAP
set -uo pipefail
TAG=$1 HEAD=$2 TRUNK=$3 WINCAP=$4
W=${W:?set W to the work directory}
S=$(cd "$(dirname "$0")" && pwd); R=$(pwd)
RUN=$W/run_$TAG; OUT=$W/out_$TAG; mkdir -p "$RUN" "$OUT"
cp /mnt/project-files/bin-cache/one_combat-83de6c12eb1130bbcdc503117fc9d96991ec3c1d256197445637e9f2c89a773f "$RUN/one_combat" || exit 3
chmod +x "$RUN/one_combat"
cp /mnt/project-files/rollout-student-494/studentc.bin "$RUN/studentc.bin" || exit 3
cp "$HEAD" "$RUN/a20.txt"   # run_unit_smoke.sh reads the head from RUN/a20.txt
sha256sum "$RUN/one_combat" "$RUN/studentc.bin" "$RUN/a20.txt" "$TRUNK"
t0=$(date +%s)
for seed in 111339997 111339998 111339999; do
  TRUNK=$TRUNK WINCAP=$WINCAP BLEND=${BLEND:-0.5} TP=${TP:-1} bash "$S/run_unit_smoke.sh" "$R" "$RUN" "$OUT" S $seed &
done
wait
echo "$TAG wall=$(( $(date +%s) - t0 ))s $(cat "$OUT"/*.done | tr '\n' ' ')"
python3 "$S/analyze2.py" "$W/$TAG.json" "$OUT" > "$W/${TAG}_analysis.txt" 2>&1
grep "head10000-base10000/all/\|stall\|validFights" "$W/${TAG}_analysis.txt" | head -12
