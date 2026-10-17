#!/usr/bin/env bash
# usage: launch.sh REPO RUN OUT -- 128 units (64 seeds x 2 arms), 8 single-thread workers, interleaved by seed
set -euo pipefail
REPO=$1 RUN=$2 OUT=$3
mkdir -p "$OUT"
for s in $(seq 111000800 111000863); do echo "control $s"; echo "ritual $s"; done |
  xargs -P 8 -L 1 bash -c 'bash "$0/docs/experiments/evidence/ritual_refit_ab_20261017/run_unit.sh" "$0" "$1" "$2" "$3" "$4"' "$REPO" "$RUN" "$OUT"
