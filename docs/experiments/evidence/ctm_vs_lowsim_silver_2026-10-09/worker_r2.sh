#!/bin/bash
# §409: CTM-only rerun of the §408 v2 seeds, scoring the Run 2 candidate CTM.
# usage: bash worker_r2.sh BINARY OUT_DIR   (from a checkout of the frozen commit)
# 16 shards of 16 seeds, the §408 v2 shard layout, four at a time.
set -euo pipefail
BIN="$1"; OUT="$2"
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ctm_vs_lowsim_silver_2026-10-09
RUN="$HOME/ctmr2-run"; mkdir -p "$RUN/cand"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
cp "$BIN" "$RUN/one_combat"
check "$RUN/one_combat" "$(cat "$D/r2-binary.sha256")"
cp /mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/prior-natpert.compact.txt "$RUN/"
check "$RUN/prior-natpert.compact.txt" 573305c48076c135f791d0712efb03be7e620aeeb961e962700ce2c60188c6ee
C=/mnt/project-files/ctm-pathb/live-ab-cloud/candidate
cp "$C/FAST-final.native" "$C/STD1-escape.native" "$C/candidate-v3.json" "$RUN/cand/"
check "$RUN/cand/FAST-final.native" 90806c25d784f7100b35ec755ad93756bf34d5aa297591891d5d3bb4314ba4f3
check "$RUN/cand/STD1-escape.native" b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf
check "$RUN/cand/candidate-v3.json" d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d
cp "$D/teacher-r2.json" "$RUN/teacher.json"
sed "s#\$RUN#$RUN#" "$D/env.sh" > "$RUN/env.sh"
. "$RUN/env.sh"
export STS_EXECUTABLE_GIT_SHA=a84be6bc4957c5fdd7245827963f88c2a18edb2d   # binary build commit
export STS_CTMSILVER_CANDIDATE_FAST="$RUN/cand/FAST-final.native" STS_CTMSILVER_CANDIDATE_STANDARD="$RUN/cand/STD1-escape.native"
export STS_CTM_RESEARCH_CANDIDATE_MANIFEST="$RUN/cand/candidate-v3.json"
export STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d
for lane in 0 1 2 3; do
  ( for i in 0 1 2 3; do
      seed=$((62100000 + 64*lane + 16*i)); name="w0${lane}s$i"; s=$(date +%s)
      rc=0
      tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen 16 0 "$OUT/$name" "$seed" "$RUN/teacher.json" 0 > "$OUT/$name.log" 2>&1 || rc=$?
      echo "$name seed=$seed rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt"
    done ) &
done
wait
[ "$(grep -c ' rc=0 ' "$OUT/shards.txt")" = 16 ] && echo "done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
cat "$OUT/shards.txt"
