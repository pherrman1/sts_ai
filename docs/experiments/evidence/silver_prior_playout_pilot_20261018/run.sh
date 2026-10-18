#!/bin/bash
# Prior-playout headroom pilot runner: 4 shards on 4 cores in one container, ctmsilvergen at Ascension 20 with the
# priorpl armset (greedy vs gen-6 E prior-argmax playouts at 2500 simulations, R = 2). Copy of the §523 run.sh.
# usage: bash run.sh OUT_DIR TOTAL BASE [SHARDS]   (run: TOTAL and BASE set at freeze, BASE = 111197692;
#        smoke: 4 111197780; rerun of a shard lost with the container: same TOTAL BASE, SHARDS "2", fresh OUT_DIR)
# Optional 5th argument: per-shard timeout (default 12h).
# Launch detached so it survives the session: setsid nohup bash run.sh OUT TOTAL BASE > OUT.log 2>&1 &
# Run from a checkout whose apps/ src/ include/ CMakeLists.txt equal code commit 6e4998e27acbf05083cba1a2967b1662a365ea3d, after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
OUT="$1"; TOTAL="$2"; BASE="$3"; SHARDS="${4:-0 1 2 3}"; LIMIT="${5:-12h}"
CODE=6eaa003489639a90afb1ad3243789e79d9b058a1
(( TOTAL % 4 == 0 )) || { echo "TOTAL must be a multiple of 4"; exit 1; }
PER=$(( TOTAL / 4 ))
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
E=docs/experiments/evidence/silver_prior_playout_pilot_20261018
git diff --quiet "$CODE" HEAD -- apps src include CMakeLists.txt || { echo "code differs from $CODE"; exit 1; }
git diff --quiet HEAD -- apps src include CMakeLists.txt "$E" || { echo "uncommitted changes"; exit 1; }
RUN="$HOME/xppl-run"; mkdir -p "$RUN"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp "$E/../silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt" "$RUN/"

check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
if [ -f "$E/BINARY_SHA256" ]; then check "$RUN/one_combat" "$(cat "$E/BINARY_SHA256")"; else echo "no BINARY_SHA256 yet (smoke only)"; fi
check "$RUN/combat_policy_mlp_g6_E.txt" ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228
# Student C out-of-combat policy (data, not code): copied from the share and hash-checked.
cp /mnt/project-files/rollout-student-494/studentc.bin "$RUN/studentc.bin"
check "$RUN/studentc.bin" eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509

sed "s#\$RUN#$RUN#g" "$E/env.sh" > "$RUN/env.sh"
. "$RUN/env.sh"
python3 tools/silver_synth_teacher.py "$CODE" "$RUN/one_combat" "$RUN/teacher.json"
"$RUN/one_combat" vwinrefreshpolicyspec "$RUN/policy.json" > /dev/null
python3 - "$RUN" <<'PY'
import json, sys
r = sys.argv[1]
t = json.load(open(f"{r}/teacher.json")); t["ooc_policy"] = json.load(open(f"{r}/policy.json"))
json.dump(t, open(f"{r}/teacher.json", "w"), indent=2)
PY
{ echo "head=$(git rev-parse HEAD) code=$CODE base=$BASE total=$TOTAL shards=$SHARDS limit=$LIMIT started=$(date -u +%FT%TZ)"
  sha256sum "$RUN/one_combat" "$RUN/combat_policy_mlp_g6_E.txt" "$RUN/studentc.bin" "$RUN/teacher.json"; } > "$OUT/FROZEN.txt"
for i in $SHARDS; do
  [[ "$i" =~ ^[0-3]$ ]] || { echo "bad shard $i"; exit 1; }
  seed=$((BASE + PER*i))
  ( s=$(date +%s)
    rc=0; timeout "$LIMIT" tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen "$PER" 20 "$OUT/shard$i" "$seed" "$RUN/teacher.json" 2 > "$OUT/shard$i.log" 2>&1 || rc=$?
    echo "shard$i seed=$seed n=$PER rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait
cat "$OUT/shards.txt"
[ "$(grep -c "rc=0" "$OUT/shards.txt")" = "$(wc -w <<< "$SHARDS")" ] && echo "done $(date -u +%FT%TZ)" > "$OUT/DONE.txt" || true
