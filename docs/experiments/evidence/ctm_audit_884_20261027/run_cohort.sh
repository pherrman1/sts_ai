#!/usr/bin/env bash
# usage: run_cohort.sh REPO RUN OUTDIR [LANES]  -- the #884 cohort: §683 MAP seeds 111374100-111374115, N=16,
# every second searched root, top 3 actions, production Silver at base 10000; LANES parallel replays (default 4).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 LANES=${4:-4}
mkdir -p "$OUT"
seq 111374100 111374115 | xargs -P "$LANES" -I{} bash "$REPO/docs/experiments/evidence/ctm_audit_884_20261027/replay_unit.sh" \
  "$REPO" "$RUN" "$OUT" {} 16 2 10000
