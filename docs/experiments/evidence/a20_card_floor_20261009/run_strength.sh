#!/usr/bin/env bash
# Combat-strength card probe (PLAN-STRENGTH.md, PLAN-SILVER-STRENGTH.md,
# PLAN-SILVER-NEXT-ACT.md): replays
# the §402 corpus source runs with the run_corpus.sh environment, one seed per
# call, TEST seeds skipped.
# usage: run_strength.sh BINARY FROZEN_SHA OUT_DIR SEED_START COUNT LANES [SEEDS_FILE SILVER_REPS NEXT_ACT]
# Lane l takes seeds START+l, START+l+LANES, ... on CPU l mod nproc. With
# SEEDS_FILE, only seeds listed there (one per line) are run, and SILVER_REPS is
# passed to the probe (0 = CTM scorer). NEXT_ACT=1 adds the next act's pools.
# Rerunning resumes: seeds with a manifest are skipped.
set -euo pipefail
BIN_SRC=$1 FROZEN=$2 OUT=$3 START=$4 COUNT=$5 LANES=$6 SEEDS_FILE=${7:-} REPS=${8:-0} NEXT_ACT=${9:-0}
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
mkdir -p "$OUT"
BIN=$(mktemp -d)/one_combat
cp "$BIN_SRC" "$BIN" && chmod +x "$BIN"
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
  python3 docs/experiments/evidence/ooc_cf_pilot_20261007/make_teacher.py "$FROZEN" "$BIN" "$OUT/policy.json" "$OUT/teacher.json"
}
sha256sum "$BIN" > "$OUT/binary.sha256"
NCPU=$(nproc)
for ((l = 0; l < LANES; l++)); do
  ( for ((s = START + l; s < START + COUNT; s += LANES)); do
      split=$(python3 -c "from tools.vwin_e3_cf import source_split; print(source_split($s))")
      [ "$split" = TEST ] && continue
      [ -n "$SEEDS_FILE" ] && ! grep -qx "$s" "$SEEDS_FILE" && continue
      prefix="$OUT/part$s"
      [ -f "$prefix.manifest.json" ] && continue
      rm -f "$prefix".states.csv "$prefix".options.csv "$prefix".strength.csv
      taskset -c $((l % NCPU)) bash tools/seed_guard.sh "$BIN" cardstrengthprobe 1 "$prefix" "$s" \
        "$OUT/teacher.json" 20 "$REPS" "$NEXT_ACT" > "$prefix.log" 2>&1 || echo "exit $?" >> "$prefix.log"
    done ) &
done
wait
echo "run done" > "$OUT/DONE"
