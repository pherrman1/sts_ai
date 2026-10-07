#!/usr/bin/env bash
# Counterfactual OOC corpus / timing runs (option 2). Run from inside the repo.
# usage: run_corpus.sh BINARY BINARY_SHA256 FROZEN_SHA OUT_DIR SEED_START SEEDS_PER_PART PARTS \
#                      FUTURES STATES_PER_SEED CARD_BOSSES [GEN] [TYPES]
# GEN=2 (generator v2, ACTION-PLAN E2) plays every branch to the end of the run;
# CARD_BOSSES is then ignored. TYPES is a comma list such as CARD_REWARD,BOSS_RELIC.
# Part p plays seeds SEED_START + p*SEEDS_PER_PART .. +SEEDS_PER_PART-1 on CPU p mod nproc.
# Rerunning resumes: finished parts (manifest present) are skipped.
set -euo pipefail
BIN_SRC=$1 BIN_SHA=$2 FROZEN=$3 OUT=$4 START=$5 PER=$6 PARTS=$7 FUTURES=$8 STATES=$9 CARDB=${10} GEN=${11:-1} TYPES=${12:-}
REPO=$(git rev-parse --show-toplevel)
HERE="$REPO/docs/experiments/evidence/ooc_cf_pilot_20261007"
cd "$REPO"
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
mkdir -p "$OUT"
BIN=$(mktemp -d)/one_combat
cp "$BIN_SRC" "$BIN" && chmod +x "$BIN"
echo "$BIN_SHA  $BIN" | sha256sum -c -
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=0 \
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 \
  STS_SILVER_LEARNED_STOP=1 OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  STS_EXECUTABLE_GIT_SHA=$FROZEN \
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_COLLECT_KEYS=0 STS_REST_WIN=0
[ -f "$OUT/teacher.json" ] || {
  "$BIN" vwinrefreshpolicyspec "$OUT/policy.json" > /dev/null
  python3 "$HERE/make_teacher.py" "$FROZEN" "$BIN" "$OUT/policy.json" "$OUT/teacher.json"
}
NCPU=$(nproc)
for ((p = 0; p < PARTS; p++)); do
  ( prefix="$OUT/part$p"
    [ -f "$prefix.manifest.json" ] && exit 0
    rm -f "$prefix".labels.csv "$prefix".options.csv "$prefix".sources.csv "$prefix".map.csv
    { time taskset -c $((p % NCPU)) bash tools/seed_guard.sh "$BIN" ooccfpilotgen "$PER" "$prefix" \
        $((START + PER * p)) "$OUT/teacher.json" "$FUTURES" "$STATES" "$CARDB" "$GEN" $TYPES ; } > "$prefix.log" 2>&1
    echo "exit $?" >> "$prefix.log" ) &
done
wait
grep -h "^ooc cf pilot\|^exit" "$OUT"/part*.log
echo "run done" > "$OUT/DONE"
