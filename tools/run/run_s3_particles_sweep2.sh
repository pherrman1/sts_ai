#!/bin/bash
# Batch 2 of the S3 particle/sims sweep: E2 + 256-seed confirmation.
#
#   pt2_p256_s4k_both_128.csv   E2: does the both-variant curve still rise at 4k?
#                               (vs p256_s3k_both = 60.9%, the batch-1 top)
#   pt2_p64_s1k_both_256.csv    efficiency point (58.6% @ 10.5 cpu-s/run at 128)
#                               paired 256-seed vs simsweep_v4_3k_256.csv (45.3%)
#   pt2_p256_s3k_both_256.csv   top win point (60.9% at 128) on the 256 block
#
# Usage: ./run_s3_particles_sweep2.sh [outdir]
set -euo pipefail
cd "$(dirname "$0")/../.."

OUTDIR=${1:-build}
BIN=${ONE_COMBAT_BIN:-./build/one_combat}
THREADS=${S3_SWEEP_THREADS:-24}

GATES=(STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
       STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
       STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
       STS_OOC_STRATEGIC_MARGIN=1.0)

echo "== S3 particle/sims sweep batch 2 =="
echo "bin:       $BIN"
echo "threads:   $THREADS"

run_arm() {
  local name=$1 sims=$2 nseeds=$3 off=$4; shift 4
  local csv="$OUTDIR/$name"
  echo "== arm $name (sims=$sims, seeds $off..$((off+nseeds-1))) -> $csv =="
  # bestbench APPENDS to an existing results file (caller owns truncation);
  # a stale/partial file silently doubles rows, so always truncate first.
  rm -f "$csv"
  env OPENBLAS_NUM_THREADS=1 STS_FAIR=1 "${GATES[@]}" "$@" \
    "$BIN" bestbench "$sims" "$nseeds" 0 "$off" "$csv"
}

run_arm pt2_p256_s4k_both_128.csv  4000 128 126700 \
  STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256
run_arm pt2_p64_s1k_both_256.csv   1000 256 126700 \
  STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
run_arm pt2_p256_s3k_both_256.csv  3000 256 126700 \
  STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256

echo "== done =="
