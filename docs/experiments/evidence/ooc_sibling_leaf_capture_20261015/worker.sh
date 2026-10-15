#!/usr/bin/env bash
# usage: worker.sh W   (W = 1..8, unpadded). Seeds 109000016+6(W-1) .. +5, A20, 4 at a time.
set -euo pipefail
W=$1; case $W in [1-8]) ;; *) echo "W must be 1..8" >&2; exit 2 ;; esac
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
E=$REPO/docs/experiments/evidence/ooc_sibling_leaf_capture_20261015
RUN=$HOME/sib-run; OUT=$HOME/sib-out/w$W; mkdir -p "$RUN" "$OUT"
cp "$REPO/build/linux-gcc-release/one_combat" "$RUN/"; (cd "$REPO"; git rev-parse HEAD) > "$RUN/GITSHA"
cp /mnt/project-files/heart1-ooc-ab-486/heart1.bin "$RUN/"
echo "1e92f2a6b2432cc9a2c67c37a7d30566dcfc7a1d45f0877f5ef697078304563f  $RUN/heart1.bin" | sha256sum -c -
export SIB_EVERY=4 SIB_REPEATS=8 SIB_LONG=4 SIB_DEPTH=2 SIB_LEAVES=256
first=$((109000016 + 6 * (W - 1)))
seq $first $((first + 5)) | xargs -P 4 -I{} bash "$E/run_unit.sh" "$REPO" "$RUN" "$OUT" cap 20 {} 1
