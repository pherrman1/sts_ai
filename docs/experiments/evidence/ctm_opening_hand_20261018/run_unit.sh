#!/usr/bin/env bash
# run_unit.sh LO N OUTDIR : guarded combattransitiongen A20, flat exact 10k Silver, both #460 row fields on.
set -uo pipefail
LO=$1 N=$2 OUT=$3
mapfile -t E < /root/ctmhand/env.txt
cd /home/user/sts_ai
st=$(date +%s)
env -i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1 "${E[@]}" bash tools/seed_guard.sh /root/ctmhand/one_combat \
  combattransitiongen "$N" 10000 20 "$OUT/u-$LO.jsonl" "$LO" /root/ctmhand/teacher.json > "$OUT/u-$LO.log" 2>&1
echo "unit=$LO n=$N rc=$? sec=$(( $(date +%s) - st ))" > "$OUT/u-$LO.done"
