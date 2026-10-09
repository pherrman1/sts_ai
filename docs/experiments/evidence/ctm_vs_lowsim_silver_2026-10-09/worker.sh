#!/bin/bash
# §408 v2 cloud worker: 4 shards of 16 seeds on 4 cores.
# usage: bash worker.sh W OUT_DIR
# Run from a checkout of the frozen commit, after a Release build of one_combat.
set -euo pipefail
W="$1"; OUT="$2"
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ctm_vs_lowsim_silver_2026-10-09
RUN="$HOME/ctmsilver-w$W"; mkdir -p "$RUN"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp /mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/prior-natpert.compact.txt "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" 0b8cddf6e92fb6cb568cf71c0f3dcdc19f22ca8f2109a3a17a311a8a61061828
check "$RUN/prior-natpert.compact.txt" 573305c48076c135f791d0712efb03be7e620aeeb961e962700ce2c60188c6ee
cp "$D/teacher.json" "$RUN/teacher.json"
sed "s#\$RUN#$RUN#" "$D/env.sh" > "$RUN/env.sh"
. "$RUN/env.sh"
for i in 0 1 2 3; do
  seed=$((62100000 + 64*W + 16*i))
  ( s=$(date +%s)
    tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen 16 0 "$OUT/shard$i" "$seed" "$RUN/teacher.json" 4 > "$OUT/shard$i.log" 2>&1
    echo "shard$i seed=$seed rc=$? wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait
grep -c "rc=0" "$OUT/shards.txt" | grep -qx 4 && echo "W=$W done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
cat "$OUT/shards.txt"
