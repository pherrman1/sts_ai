#!/bin/bash
# §455 cloud worker: 4 shards on 4 cores (plain2k, plain_cpu 2300, MLP gen-1 tree prior K=8 at 2k).
# usage: bash worker.sh W N OUT_DIR    (W = 1..N, N divides 32: 8 or 16 workers)
# Run from a checkout of 4f0cfb4c after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
W="$1"; N="$2"; OUT="$3"
D=/mnt/project-files/silver-az-mlp/gen1-eval
TOTAL=128; BASE=85000000
(( N >= 1 && 32 % N == 0 && W >= 1 && W <= N )) || { echo "bad W/N: $W/$N"; exit 1; }
PER=$(( TOTAL / N / 4 ))
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = 4f0cfb4c7c1297fc9393f2ead01505e3fda06f9b ] || { echo "checkout is not 4f0cfb4c"; exit 1; }
RUN="$HOME/gen1eval-w$W"; mkdir -p "$RUN"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp "$D/combat_policy_mlp_gen1.txt" "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$(cat "$D/BINARY_SHA256")"
check "$RUN/combat_policy_mlp_gen1.txt" a5f4505acd1f920958efc8476ff66127eadafed49ed719596e630c5d9adc64d2
python3 tools/silver_synth_teacher.py 4f0cfb4c7c1297fc9393f2ead01505e3fda06f9b "$RUN/one_combat" "$RUN/teacher.json"
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
  seed=$((BASE + 4*PER*(W-1) + PER*i))
  ( s=$(date +%s)
    rc=0; tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen "$PER" 0 "$OUT/shard$i" "$seed" "$RUN/teacher.json" 2 > "$OUT/shard$i.log" 2>&1 || rc=$?
    echo "shard$i seed=$seed n=$PER rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait
grep -c "rc=0" "$OUT/shards.txt" | grep -qx 4 && echo "W=$W N=$N done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
cat "$OUT/shards.txt"
