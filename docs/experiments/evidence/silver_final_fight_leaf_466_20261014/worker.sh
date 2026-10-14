#!/bin/bash
# Final-fight leaf replay (ctmsilvergen, STS_CTMSILVER_ARMSET=finalleaf) on 4 cores.
# usage: bash worker.sh COMMIT BASE_SEED SEEDS_PER_SHARD SHARDS REPLICATES OUT_DIR
# Run from a checkout of COMMIT after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
COMMIT="$1"; BASE="$2"; PER="$3"; SHARDS="$4"; R="$5"; OUT="$6"
D=/mnt/project-files/silver-leaf-situational
PRIOR_SRC=/mnt/project-files/silver-az-mlp/gen3-eval/combat_policy_mlp_gen3.txt
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = "$COMMIT" ] || { echo "checkout is not $COMMIT"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "tracked changes in checkout"; exit 1; }
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
RUN="$OUT.run"; mkdir -p "$RUN" "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp "$PRIOR_SRC" "$RUN/prior.txt"
[ "$(sha256sum "$RUN/prior.txt" | cut -d' ' -f1)" = f57b7fdd728a4086a00ac7fd6eafa5d393723789d38a330bf676599ef0da5315 ] || { echo "prior sha mismatch"; exit 1; }
sha256sum "$RUN/one_combat" | cut -d' ' -f1 > "$OUT/BINARY_SHA256"
python3 tools/silver_synth_teacher.py "$COMMIT" "$RUN/one_combat" "$RUN/teacher.json"
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0
export STS_EXECUTABLE_GIT_SHA="$COMMIT"
# The root prior is required by the harness but unused: every finalleaf arm runs with the prior off.
export STS_SILVER_ROOT_PRIOR="$RUN/prior.txt" STS_SILVER_ROOT_PRIOR_WEIGHT=400 OMP_NUM_THREADS=1
export STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
export STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_REST_WIN=0
export STS_CTMSILVER_ARMSET=finalleaf
env | grep -E '^(STS_|OMP_)' | sort > "$OUT/env.txt"
"$RUN/one_combat" vwinrefreshpolicyspec "$RUN/policy.json" > /dev/null
python3 - "$RUN" <<'PY'
import json, sys
r = sys.argv[1]
t = json.load(open(f"{r}/teacher.json")); t["ooc_policy"] = json.load(open(f"{r}/policy.json"))
json.dump(t, open(f"{r}/teacher.json", "w"), indent=2)
PY
cp "$RUN/teacher.json" "$OUT/teacher.json"
for i in $(seq 0 $((SHARDS-1))); do
  seed=$((BASE + PER*i))
  ( s=$(date +%s)
    rc=0; tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen "$PER" 0 "$OUT/shard$i" "$seed" "$RUN/teacher.json" "$R" > "$OUT/shard$i.log" 2>&1 || rc=$?
    echo "shard$i seed=$seed n=$PER rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait
[ "$(grep -c "rc=0" "$OUT/shards.txt")" = "$SHARDS" ] && echo "done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
cat "$OUT/shards.txt"
