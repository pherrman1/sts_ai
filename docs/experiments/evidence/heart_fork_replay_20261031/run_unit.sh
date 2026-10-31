#!/usr/bin/env bash
# Fresh Heart replay of run-1 forks at production search (README.md). usage: run_unit.sh REPO RUN UNIT_OUT FILE
# FILE = one Heart-entry state (SEED-bNN.jsonl in fork_states.tar), rebuilt from run 1 fork NN's CTM pre row.
# one_combat act4replay, battle seed = the entry's SEED (same as the #923 control), 2 replicates.
# Silver as production's Act-4 Heart (ADR-0060): flat 40,000 per root, exact root budgets (every root searched),
# node reuse cap 262,144, g7f_E root table and prior, boss prior playouts. 4 h timeout (rc 124).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 F=$4
[[ "$F" =~ ^[0-9]+-b[0-9][0-9]\.jsonl$ ]] || { echo "bad unit $F" >&2; exit 2; }
B=${F%.jsonl}; SEED=${B%%-*}
mkdir -p "$OUT/in"
tar -xf "$RUN/fork_states.tar" -C "$OUT/in" "$F" || { echo "cannot extract $F" >&2; exit 2; }
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_COLLECT_KEYS=1 STS_FAIR=1 STS_ACTIVE_POWER_FEATURES=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_REUSE_CAP_MODE=allocated
  STS_SILVER_LEARNED_STOP=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_NODE_REUSE_CAP=262144
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8)
cd "$REPO" || exit 2
printf '%s\n' "${E[@]}" | grep '^STS_' > "$OUT/$B.env"
start=$(date -u +%FT%TZ); t0=$(date +%s)
env -i "${E[@]}" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" act4replay 1 "$OUT/in/$F" "$OUT/$B" "$SEED" 40000 2 \
  > "$OUT/$B.log" 2>&1
rc=$?
if [ "$rc" = 0 ]; then
  [ "$(grep -c ',fair,flat$' "$OUT/$B.csv")" = 2 ] || rc=93
  grep -q "flat budget; exact root budgets" "$OUT/$B.log" || rc=94
  grep -q "research node reuse cap 262144" "$OUT/$B.log" || rc=95
fi
rm -rf "$OUT/in"
echo "tag=$B rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/$B.done"
exit $rc
