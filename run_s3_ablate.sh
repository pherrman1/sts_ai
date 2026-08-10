#!/bin/bash
# S3 feature ablation at the recommended operating point (V4 gate stack, fair,
# A0, 3,000 sims/decision). Each S3-only mechanism is removed in isolation:
#
#   A0 s2_ref     Searcher2 reference (no S3)
#   A1 s3_ctl     Searcher3 full package (control)
#   A2 s3_nobel   S3 minus particle belief reweighting (STS_S3_BELIEF=0)
#   A3 s3_noprune S3 minus canPruneAsDead (STS_S3_PRUNE=0)
#   A4 s3_nochain S3 minus deterministic chain compression (STS_S3_CHAIN=0)
#   A5 s3_nolive  S3 minus live-valid root-edge filter (STS_S3_LIVE=0;
#                 Searcher2-style most-visited edge, invalid edge ends battle)
#   A6 s3_crn     S3 plus root CRN warm start (STS_S3_CRN=1, opt-in; fires once
#                 per fresh searcher, skipped on tree carry-over)
#
# References (recorded, pair against the 128-block slice):
#   build/simsweep_v4_3k_256.csv, seeds <= 126827: 56/128 = 43.75% (S2@3k, V4
#   gates). A0 re-measures the S2@3k reference on THIS binary so the comparison
#   is free of binary drift; it must reproduce 43.75% (0 non-sec diffs).
#
# Prerequisites on the server:
#   - sources synced to the local HEAD with the STS_S3_* flags,
#   - `cmake --build build -j --target one_combat` run,
#   - artifacts present with the hashes verified below.
#
# Usage: ./run_s3_ablate.sh [seeds] [offset] [outdir]
set -euo pipefail
cd "$(dirname "$0")"

NSEEDS=${1:-128}
SEED_OFF=${2:-126700}
OUTDIR=${3:-build}
BIN=${ONE_COMBAT_BIN:-./build/one_combat}
THREADS=${S3_ABLATE_THREADS:-24}
SIMS=3000

# V4 full gate stack (EXPERIMENTS.md §99): tok net + REST/EVENT/SHOP/TREASURE/
# BOSS_RELIC=1, margin 1.0, map gate off.
GATES=(STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
       STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
       STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
       STS_OOC_STRATEGIC_MARGIN=1.0)

echo "== S3 feature ablation =="
echo "bin:       $BIN"
echo "threads:   $THREADS"
echo "sims:      $SIMS"
echo "seeds:     $SEED_OFF..$((SEED_OFF+NSEEDS-1))"
echo "gates:     V4 full stack (tok net + REST/EVENT/SHOP/TREASURE/BOSS_RELIC, margin 1.0, MAP off)"

# Artifact identity (must match the recorded §99/§101 set).
sha256sum selfplay/models/ooc_strategic_tok_final.native models/policy_trees_c.txt

run_arm() {
  local name=$1; shift
  local csv="$OUTDIR/$name"
  # bestbench APPENDS to an existing results file (caller owns truncation);
  # a stale/partial file silently doubles rows, so always truncate first.
  rm -f "$csv"
  echo "== arm $name -> $csv =="
  env OPENBLAS_NUM_THREADS=1 STS_FAIR=1 "${GATES[@]}" "$@" \
    "$BIN" bestbench "$SIMS" "$NSEEDS" 0 "$SEED_OFF" "$csv"
}

run_arm s3ablate_s2_ref_3k_128.csv
run_arm s3ablate_s3_ctl_3k_128.csv       STS_SEARCHER3=1
run_arm s3ablate_s3_nobel_3k_128.csv     STS_SEARCHER3=1 STS_S3_BELIEF=0
run_arm s3ablate_s3_noprune_3k_128.csv   STS_SEARCHER3=1 STS_S3_PRUNE=0
run_arm s3ablate_s3_nochain_3k_128.csv   STS_SEARCHER3=1 STS_S3_CHAIN=0
run_arm s3ablate_s3_nolive_3k_128.csv    STS_SEARCHER3=1 STS_S3_LIVE=0
run_arm s3ablate_s3_crn_3k_128.csv       STS_SEARCHER3=1 STS_S3_CRN=1

echo "== done; aggregate (requires local pandas; CSVs are on the server in $OUTDIR) =="
if python3 -c "import pandas" 2>/dev/null; then
  for f in "$OUTDIR"/s3ablate_*_3k_128.csv; do
    python3 - "$f" <<'PY'
import sys, pandas as pd
f = sys.argv[1]
df = pd.read_csv(f)
print(f"{f}: n={len(df)} wins={int(df.won.sum())} rate={df.won.mean():.4f} "
      f"floor={df.floor.mean():.2f} hpEnd={df.hpEnd.mean():.2f} "
      f"sec/run={df.sec.mean():.2f}")
PY
  done
else
  echo "pandas missing on this host; run the paired analysis locally."
fi
