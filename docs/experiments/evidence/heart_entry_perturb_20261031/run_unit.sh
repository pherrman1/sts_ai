#!/usr/bin/env bash
# Heart-entry perturbation labels (PREREG.md). usage: run_unit.sh REPO RUN UNIT_OUT I -- base state I (0-based line of
# every v<k>.jsonl in variants.tar) played once per variant k = 0..15 and replicate r = 0..1 with one_combat act4replay.
# Replicate r uses battle seed BLOCK[r] + I; every variant of base I shares the battle and planner seed of its
# replicate, so variants differ only in the state change. Silver as the Incense probe (§723): learned stop
# (gbt-0cac7cc64364, <= 10k per root, no boss extension), one-action roots unsearched, Act 4 strong off, node reuse cap
# 262,144, g7f_E root table and prior, boss prior playouts. Always exits 0 (rc in the .done line); 2 h timeout per fight.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 I=$4
[[ "$I" =~ ^[0-9]+$ ]] && [ "$I" -lt 600 ] || { echo "bad base index $I" >&2; exit 2; }
mkdir -p "$OUT/in"
tar -xf "$RUN/variants.tar" -C "$OUT/in" || { echo "cannot extract variants.tar" >&2; exit 2; }
BLOCKS=(111384000 111382000)
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_COLLECT_KEYS=1 STS_FAIR=1 STS_ACTIVE_POWER_FEATURES=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_REUSE_CAP_MODE=allocated
  STS_ACT4REPLAY_BUDGET=learned STS_SILVER_LEARNED_STOP=1 STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364
  STS_SILVER_ACT4_STRONG=0 STS_SILVER_EXACT_ROOT_BUDGETS=0 STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=0
  STS_SILVER_NODE_REUSE_CAP=262144
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8)
cd "$REPO" || exit 2
printf '%s\n' "${E[@]}" | grep '^STS_' > "$OUT/u$I.env"
start=$(date -u +%FT%TZ); t0=$(date +%s); rc=0
for k in $(seq 0 15); do
  sed -n "$((I + 1))p" "$OUT/in/v$k.jsonl" > "$OUT/s$I-v$k.jsonl"
  [ -s "$OUT/s$I-v$k.jsonl" ] || { rc=96; break; }
  for r in 0 1; do
    tag="u$I-v$k-r$r"
    env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" act4replay 1 "$OUT/s$I-v$k.jsonl" "$OUT/$tag" \
      "$((BLOCKS[r] + I))" 10000 1 > "$OUT/$tag.log" 2>&1
    x=$?; [ "$x" = 0 ] || { rc=$x; continue; }
    [ "$(grep -c ',learned$' "$OUT/$tag.csv")" = 1 ] || rc=93
    grep -q "learned stop gbt-0cac7cc64364; one-action roots unsearched" "$OUT/$tag.log" || rc=94
    grep -q "research node reuse cap 262144" "$OUT/$tag.log" || rc=95
  done
done
rm -rf "$OUT/in"
echo "tag=u$I rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/u$I.done"
exit 0
