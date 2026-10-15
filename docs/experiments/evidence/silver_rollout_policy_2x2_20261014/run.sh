#!/bin/bash
# §479 runner: 4 shards on 4 cores in one container, ctmsilvergen at Ascension 20 with the
# rollout479 armset (greedy / uniform / per-leaf / card-table rollouts × no prior / gen-6 E, R = 2).
# usage: bash run.sh OUT_DIR TOTAL BASE [SHARDS]   (run: TOTAL and BASE set at freeze, BASE >= 105000000;
#        smoke: 4 74071490; 8 workers: 8 $((105000000 + 8*(W-1))) "0 1 2 3" 6h; rerun of a shard lost with the container: same TOTAL BASE, SHARDS "2", fresh OUT_DIR)
# Optional 5th argument: per-shard timeout (default 12h).
# Launch detached so it survives the session: setsid nohup bash run.sh OUT TOTAL BASE > OUT.log 2>&1 &
# Run from a checkout whose apps/ src/ include/ CMakeLists.txt equal code commit 7a413622, after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
OUT="$1"; TOTAL="$2"; BASE="$3"; SHARDS="${4:-0 1 2 3}"; LIMIT="${5:-12h}"
CODE=7a413622b47f91e11b7ae12e749fc27502948619
(( TOTAL % 4 == 0 )) || { echo "TOTAL must be a multiple of 4"; exit 1; }
PER=$(( TOTAL / 4 ))
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
E=docs/experiments/evidence/silver_rollout_policy_2x2_20261014
git diff --quiet "$CODE" HEAD -- apps src include CMakeLists.txt || { echo "code differs from $CODE"; exit 1; }
git diff --quiet HEAD -- apps src include CMakeLists.txt "$E" || { echo "uncommitted changes"; exit 1; }
RUN="$HOME/x479-run"; mkdir -p "$RUN"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp "$E/../silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt" "$RUN/"
cp "$E/card_table/card_table_g6.txt" "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$(cat "$E/BINARY_SHA256")"
check "$RUN/combat_policy_mlp_g6_E.txt" ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228
check "$RUN/card_table_g6.txt" fa93269f251bda03da879f5a1ff68bc3746d79d4887c8ae0ad25ae465b725c98
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
{ echo "head=$(git rev-parse HEAD) code=$CODE base=$BASE total=$TOTAL shards=$SHARDS limit=$LIMIT started=$(date -u +%FT%TZ)"
  sha256sum "$RUN/one_combat" "$RUN/combat_policy_mlp_g6_E.txt" "$RUN/card_table_g6.txt" "$RUN/teacher.json"; } > "$OUT/FROZEN.txt"
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
