#!/bin/bash
# §452 cloud worker: 4 shards on 4 cores (tree-prior fight-level pilot).
# usage: bash worker.sh W OUT_DIR SEEDS_PER_SHARD
# Run from a checkout of the frozen commit after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
W="$1"; OUT="$2"; PER="$3"
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/silver_tree_prior_20261012
RUN="$HOME/treeprior-w$W"; mkdir -p "$RUN"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp /mnt/project-files/silver-tree-prior-452/inputs/prior-natpert.compact.txt "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$(cat "$D/BINARY_SHA256")"
check "$RUN/prior-natpert.compact.txt" 573305c48076c135f791d0712efb03be7e620aeeb961e962700ce2c60188c6ee
python3 tools/silver_synth_teacher.py "$(cat "$D/RUN_GIT_SHA")" "$RUN/one_combat" "$RUN/teacher.json"
sed "s#\$RUN#$RUN#g" "$D/env.sh" > "$RUN/env.sh"
. "$RUN/env.sh"
"$RUN/one_combat" vwinrefreshpolicyspec "$RUN/policy.json" > /dev/null
python3 - "$RUN" <<'PY'
import json, sys
r = sys.argv[1]
t = json.load(open(f"{r}/teacher.json")); t["ooc_policy"] = json.load(open(f"{r}/policy.json"))
json.dump(t, open(f"{r}/teacher.json", "w"), indent=2)
PY
for i in 0 1 2 3; do
  seed=$((84000000 + 16*PER*(W-1) + PER*i))
  ( s=$(date +%s)
    rc=0; tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen "$PER" 0 "$OUT/shard$i" "$seed" "$RUN/teacher.json" 2 > "$OUT/shard$i.log" 2>&1 || rc=$?
    echo "shard$i seed=$seed n=$PER rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait
grep -c "rc=0" "$OUT/shards.txt" | grep -qx 4 && echo "W=$W done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
cat "$OUT/shards.txt"
