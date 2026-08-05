#!/bin/bash
# Particle-count x sim-budget sweep for the S3 -belief variants, at the
# recommended operating point (V4 gate stack, fair, A0). Follows EXPERIMENTS.md
# §106: belief reweighting and chain compression are net-negative, so the sweep
# screens S3-belief (A2) and S3-belief-chain (A7) across particle counts, plus
# one belief-ON control at 256 particles (E1: is the belief harm a capacity
# limit?).
#
# Batch 1 (13 arms, 128 seeds):
#   pt_sweep_p{16,64,256}_s{1k,3k}_belf    S3 -belief
#   pt_sweep_p{16,64,256}_s{1k,3k}_both    S3 -belief -chain
#   pt_sweep_p256_s3k_ctl                  S3 full, 256 particles (E1)
#
# In-grid anchors (recorded §106, 128 seeds): A2@64/3k = 57.8%, S3 ctl = 49.2%,
# S2 ref = 43.8% (build/s3ablate_*_3k_128.csv). pt_sweep_p64_s3k_belf re-runs
# the recorded A2 point on THIS binary (0 non-sec diffs expected).
#
# Usage: ./run_s3_particles_sweep.sh [seeds] [offset] [outdir]
set -euo pipefail
cd "$(dirname "$0")"

NSEEDS=${1:-128}
SEED_OFF=${2:-126700}
OUTDIR=${3:-build}
BIN=${ONE_COMBAT_BIN:-./build/one_combat}
THREADS=${S3_SWEEP_THREADS:-24}

GATES=(STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
       STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
       STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
       STS_OOC_STRATEGIC_MARGIN=1.0)

echo "== S3 particle x sims sweep (batch 1) =="
echo "bin:       $BIN"
echo "threads:   $THREADS"
echo "seeds:     $SEED_OFF..$((SEED_OFF+NSEEDS-1))"
echo "gates:     V4 full stack (tok net + REST/EVENT/SHOP/TREASURE/BOSS_RELIC, margin 1.0, MAP off)"

sha256sum selfplay/models/ooc_strategic_tok_final.native build/policy_trees_c.txt

run_arm() {
  local name=$1 sims=$2; shift 2
  local csv="$OUTDIR/$name"
  echo "== arm $name (sims=$sims) -> $csv =="
  # bestbench APPENDS to an existing results file (caller owns truncation);
  # a stale/partial file silently doubles rows, so always truncate first.
  rm -f "$csv"
  env OPENBLAS_NUM_THREADS=1 STS_FAIR=1 "${GATES[@]}" "$@" \
    "$BIN" bestbench "$sims" "$NSEEDS" 0 "$SEED_OFF" "$csv"
}

# S3 -belief grid
run_arm pt_sweep_p16_s1k_belf.csv  1000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_PARTICLES=16
run_arm pt_sweep_p64_s1k_belf.csv  1000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_PARTICLES=64
run_arm pt_sweep_p256_s1k_belf.csv 1000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_PARTICLES=256
run_arm pt_sweep_p16_s3k_belf.csv  3000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_PARTICLES=16
run_arm pt_sweep_p64_s3k_belf.csv  3000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_PARTICLES=64
run_arm pt_sweep_p256_s3k_belf.csv 3000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_PARTICLES=256
# S3 -belief -chain grid
run_arm pt_sweep_p16_s1k_both.csv  1000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=16
run_arm pt_sweep_p64_s1k_both.csv  1000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
run_arm pt_sweep_p256_s1k_both.csv 1000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256
run_arm pt_sweep_p16_s3k_both.csv  3000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=16
run_arm pt_sweep_p64_s3k_both.csv  3000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
run_arm pt_sweep_p256_s3k_both.csv 3000 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256
# E1: belief ON at 256 particles (capacity question)
run_arm pt_sweep_p256_s3k_ctl.csv  3000 STS_SEARCHER3=1 STS_S3_PARTICLES=256

echo "== done; aggregate (requires local pandas; CSVs are on the server in $OUTDIR) =="
if python3 -c "import pandas" 2>/dev/null; then
  for f in "$OUTDIR"/pt_sweep_*_128.csv; do
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
