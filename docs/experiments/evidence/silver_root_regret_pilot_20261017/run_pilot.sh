#!/bin/bash
# Root-regret pilot: 4 shards of ctmsilvergen with STS_CTMSILVER_ARMSET=rootregret at A20 (§518 environment).
# usage: bash run_pilot.sh OUT TOTAL BASE EVERY   (ONE_COMBAT=<binary> overrides build/linux-gcc-release/one_combat)
# §526 ran at 80530a06, before ADR-0046 made the rollout root table default on; on later code this script sets
# STS_SILVER_ROLLOUT_ROOT_TABLE=0 to reproduce it (at 80530a06 the variable must stay unset: "0" would be read as a path).
set -euo pipefail
OUT="$1"; TOTAL="$2"; BASE="$3"; EVERY="$4"; PER=$(( TOTAL / 4 ))
REPO=/home/user/sts_ai; cd "$REPO"
RUN=$HOME/rr-run-$(basename "$OUT"); mkdir -p "$RUN" "$OUT"
cp "${ONE_COMBAT:-build/linux-gcc-release/one_combat}" "$RUN/one_combat"
cp docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt "$RUN/"
cp /mnt/project-files/rollout-student-494/studentc.bin "$RUN/studentc.bin"
CODE=$(git rev-parse HEAD)
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_LEARNED_STOP=0
export STS_EXECUTABLE_GIT_SHA=$CODE
export STS_SILVER_ROOT_PRIOR=$RUN/combat_policy_mlp_g6_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 OMP_NUM_THREADS=1
export STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
export STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_REST_WIN=0
export STS_COLLECT_KEYS=0 STS_OOC_HEART1=$RUN/studentc.bin
export STS_CTMSILVER_ARMSET=rootregret STS_CTMSILVER_HALLWAY_EVERY=3 STS_CTMSILVER_MLP_PRIOR=$RUN/combat_policy_mlp_g6_E.txt
export STS_CTMSILVER_ROOT_EVERY=$EVERY
if grep -q "ADR-0046 default on" src/sim/search/NativeSilverBackend.cpp; then export STS_SILVER_ROLLOUT_ROOT_TABLE=0; fi
[ -f "$RUN/teacher.json" ] || { python3 tools/silver_synth_teacher.py "$CODE" "$RUN/one_combat" "$RUN/teacher.json"
  "$RUN/one_combat" vwinrefreshpolicyspec "$RUN/policy.json" > /dev/null
  python3 - "$RUN" <<'PY'
import json, sys
r = sys.argv[1]
t = json.load(open(f"{r}/teacher.json")); t["ooc_policy"] = json.load(open(f"{r}/policy.json"))
json.dump(t, open(f"{r}/teacher.json", "w"), indent=2)
PY
}
{ echo "code=$CODE base=$BASE total=$TOTAL every=$EVERY started=$(date -u +%FT%TZ)"; sha256sum "$RUN/one_combat" "$RUN"/*.txt "$RUN/studentc.bin" "$RUN/teacher.json"; } > "$OUT/FROZEN.txt"
for i in 0 1 2 3; do
  seed=$((BASE + PER*i))
  ( rc=0; s=$(date +%s); tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen "$PER" 20 "$OUT/shard$i" "$seed" "$RUN/teacher.json" 1 > "$OUT/shard$i.log" 2>&1 || rc=$?
    echo "shard$i seed=$seed n=$PER rc=$rc wall=$(( $(date +%s)-s ))" >> "$OUT/shards.txt" ) &
done
wait; cat "$OUT/shards.txt"
