#!/usr/bin/env bash
# README analysis step 6: one leaf net in the fight-level A/B harness, as ../silver_leaf_label_data_20261023/smoke/
# run_smoke.sh (one_combat 83de6c12..., the A/B's binary; its run_unit_smoke.sh unchanged) at blend 0.5, no turn
# penalty, no win-now cap, on 16 sources: 111339997-999 (the earlier smokes') and 111391000-012 (reserved for this
# round), four at a time. Arms base10000 (production) and head10000 (the net as leaf); pair.py compares two runs.
# usage (repo root): W=WORKDIR run_smoke16.sh TAG HEAD TRUNK
set -uo pipefail
TAG=$1 HEAD=$2 TRUNK=$3
W=${W:?set W to the work directory}
E=$(cd "$(dirname "$0")" && pwd); L=$E/../silver_leaf_label_data_20261023/smoke; R=$(pwd)
RUN=$W/run_$TAG; OUT=$W/out_$TAG; mkdir -p "$RUN" "$OUT"
cp /mnt/project-files/bin-cache/one_combat-83de6c12eb1130bbcdc503117fc9d96991ec3c1d256197445637e9f2c89a773f "$RUN/one_combat" || exit 3
chmod +x "$RUN/one_combat"
cp /mnt/project-files/rollout-student-494/studentc.bin "$RUN/studentc.bin" || exit 3
cp "$HEAD" "$RUN/a20.txt"   # run_unit_smoke.sh reads the head from RUN/a20.txt
sha256sum "$RUN/one_combat" "$RUN/studentc.bin" "$RUN/a20.txt" "$TRUNK"
t0=$(date +%s)
printf '%s\n' 111339997 111339998 111339999 $(seq 111391000 111391012) \
  | TRUNK=$TRUNK WINCAP=0 BLEND=0.5 TP=0 xargs -P 4 -I{} bash "$L/run_unit_smoke.sh" "$R" "$RUN" "$OUT" S {}
echo "$TAG wall=$(( $(date +%s) - t0 ))s $(cat "$OUT"/*.done | tr '\n' ' ')"
python3 "$L/analyze2.py" "$W/$TAG.json" "$OUT" > "$W/${TAG}_analysis.txt" 2>&1
grep "head10000-base10000/all/\|stall\|validFights" "$W/${TAG}_analysis.txt" | head -12
