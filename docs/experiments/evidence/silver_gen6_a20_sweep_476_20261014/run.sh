#!/bin/bash
# §476 runner: 4 shards on 4 cores in one container, ctmsilvergen at Ascension 20 with the
# mlpsweep armset (plain / gen-6 E / gen-5 at 10000, 2500, 625 simulations, R = 2).
# usage: bash run.sh OUT_DIR [TOTAL BASE]   (defaults: 96 seeds from 104000000; smoke: 4 74071200)
# Run from a checkout whose apps/ src/ CMakeLists.txt equal code commit 339da3b1, after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
OUT="$1"; TOTAL="${2:-96}"; BASE="${3:-104000000}"
CODE=339da3b178a1342e1618a71f883c148b08196adb
(( TOTAL % 4 == 0 )) || { echo "TOTAL must be a multiple of 4"; exit 1; }
PER=$(( TOTAL / 4 ))
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
E=docs/experiments/evidence/silver_gen6_a20_sweep_476_20261014
git diff --quiet "$CODE" HEAD -- apps src CMakeLists.txt || { echo "code differs from $CODE"; exit 1; }
git diff --quiet HEAD -- apps src CMakeLists.txt "$E" || { echo "uncommitted changes"; exit 1; }
RUN="$HOME/x476-run"; mkdir -p "$RUN"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp "$E/../silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt" "$RUN/"
cp "$E/combat_policy_mlp_gen5.txt" "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$(cat "$E/BINARY_SHA256")"
check "$RUN/combat_policy_mlp_g6_E.txt" ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228
check "$RUN/combat_policy_mlp_gen5.txt" 5e9f975a35c0277e773fc0fc6d5f21564d75a66918e655f695f6efd1aac89e8a
python3 tools/silver_synth_teacher.py "$CODE" "$RUN/one_combat" "$RUN/teacher.json"
sed "s#\$RUN#$RUN#g" "$E/env.sh" > "$RUN/env.sh"
. "$RUN/env.sh"
"$RUN/one_combat" vwinrefreshpolicyspec "$RUN/policy.json" > /dev/null
python3 - "$RUN" <<'PY'
import json, sys
r = sys.argv[1]
t = json.load(open(f"{r}/teacher.json")); t["ooc_policy"] = json.load(open(f"{r}/policy.json"))
json.dump(t, open(f"{r}/teacher.json", "w"), indent=2)
PY
{ echo "head=$(git rev-parse HEAD) code=$CODE base=$BASE total=$TOTAL started=$(date -u +%FT%TZ)"
  sha256sum "$RUN/one_combat" "$RUN"/combat_policy_mlp_*.txt "$RUN/teacher.json"; } > "$OUT/FROZEN.txt"
for i in 0 1 2 3; do
  seed=$((BASE + PER*i))
  ( s=$(date +%s)
    rc=0; timeout 6h tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen "$PER" 20 "$OUT/shard$i" "$seed" "$RUN/teacher.json" 2 > "$OUT/shard$i.log" 2>&1 || rc=$?
    echo "shard$i seed=$seed n=$PER rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait
cat "$OUT/shards.txt"
grep -c "rc=0" "$OUT/shards.txt" | grep -qx 4 && echo "done $(date -u +%FT%TZ)" > "$OUT/DONE.txt" || true
