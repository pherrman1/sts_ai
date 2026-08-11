#!/bin/bash
# Phase 1 payoff gate: does Searcher3+PVNet have a channel at the 3k-sim
# operating point of the recommended Searcher2 config?
#
# Arms (fair, A0, 3,000 sims/decision, 128 seeds 126700-126827, 24 threads):
#   0. Searcher2 fresh same-binary reference          -> pvnetgate_s2_ref_3k_128.csv
#   1. Searcher3 control (no PVNet)                   -> pvnetgate_s3_ctl_3k_128.csv
#   2. Searcher3 + PVNet alpha=0 (policy priors only) -> pvnetgate_s3_pv0_3k_128.csv
#   3. Searcher3 + PVNet alpha=1.0 (pure neural leaf) -> pvnetgate_s3_pv1_3k_128.csv
#
# Reference (recorded, pair against the 128-block slice):
#   build/simsweep_v4_3k_256.csv, seeds <= 126827: 56/128 = 43.75% (S2@3k, V4 gates).
# Arm 0 re-measures the S2@3k reference on THIS binary so the comparison is
# free of binary drift.
#
# Prerequisites on the server:
#   - sources synced to the local HEAD containing the PVNet parity fixes
#     (src/sim/search/CombatPVNet.cpp gelu/14-token/policy-dot-product),
#   - `cmake --build build -j --target one_combat` run,
#   - artifacts present with the hashes verified below.
#
# Usage: ./run_pvnet_gate.sh [seeds] [offset] [outdir]
set -euo pipefail
cd "$(dirname "$0")"

NSEEDS=${1:-128}
SEED_OFF=${2:-126700}
OUTDIR=${3:-build}
BIN=${ONE_COMBAT_BIN:-./build/one_combat}
THREADS=${PVNET_GATE_THREADS:-24}
SIMS=3000

echo "== PVNet payoff gate =="
echo "bin:       $BIN"
echo "threads:   $THREADS"
echo "sims:      $SIMS"
echo "seeds:     $SEED_OFF..$((SEED_OFF+NSEEDS-1))"

# Artifact identity (must match local HEAD; the binary must contain pvnetparity)
sha256sum models/v_combat_pvnet.txt models/policy_trees_c.txt 2>/dev/null || true
if ! "$BIN" pvnetparity models/v_combat_pvnet.txt /nonexistent_parity.csv 2>&1 \
     | grep -q "PVNET VALIDATION"; then
  echo "ERROR: binary lacks pvnetparity mode - parity-fixed build required" >&2
  exit 1
fi

run_arm() {
  local name=$1; shift
  local csv="$OUTDIR/$name"
  local s3flag=$1; shift
  echo "== arm $name -> $csv (searcher3=$s3flag) =="
  # OPENBLAS_NUM_THREADS=1: the 24 outer OpenMP workers each call BLAS; letting
  # OpenBLAS spawn its own pool oversubscribes the box ~2x (load ~47 on 24
  # cores) and runs SLOWER than scalar. One thread per call is the fast path.
  # s3flag controls STS_SEARCHER3 per arm: arm 0 (true S2 reference) must NOT
  # set it (the first gate run set it for every arm, silently turning the
  # "S2 reference" into an S3 duplicate).
  env OPENBLAS_NUM_THREADS=1 STS_FAIR=1 $s3flag "$@" \
    "$BIN" bestbench "$SIMS" "$NSEEDS" 0 "$SEED_OFF" "$csv"
}

run_arm pvnetgate_s2_ref_3k_128.csv ""
run_arm pvnetgate_s3_ctl_3k_128.csv "STS_SEARCHER3=1"
run_arm pvnetgate_s3_pv0_3k_128.csv "STS_SEARCHER3=1" \
  STS_PVNET=models/v_combat_pvnet.txt STS_PVNET_ALPHA=0
run_arm pvnetgate_s3_pv1_3k_128.csv "STS_SEARCHER3=1" \
  STS_PVNET=models/v_combat_pvnet.txt STS_PVNET_ALPHA=1.0

echo "== done; aggregate: =="
for f in "$OUTDIR"/pvnetgate_s3_*_3k_128.csv; do
  python3 - "$f" <<'PY'
import sys, pandas as pd
f = sys.argv[1]
df = pd.read_csv(f)
print(f"{f}: n={len(df)} wins={int(df.won.sum())} rate={df.won.mean():.4f} "
      f"floor={df.floor.mean():.2f} hpEnd={df.hpEnd.mean():.2f} "
      f"sec/run={df.sec.mean():.2f}")
PY
done
