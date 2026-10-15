#!/usr/bin/env bash
# Sibling-leaf capture cloud worker.  usage: worker.sh setup|run|status W   (W = 1..8, unpadded)
# Worker W runs A20 seeds 109000016+6(W-1) .. +5 (the lead container runs 109000000-015), 4 units at a time,
# then uploads /mnt/project-files/leaf-value-gate/wWW.tar.gz and wWW.DONE.txt.
set -uo pipefail
MODE=${1:-}; W=${2:-}
case $W in [1-8]) ;; *) echo "STOP: W must be 1..8 (unpadded)"; exit 2 ;; esac
WW=$(printf %02d "$W")
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
E=$REPO/docs/experiments/evidence/ooc_sibling_leaf_capture_20261015
BASE=$HOME/sib-w$WW; RUN=$BASE/run; OUT=$BASE/out; SHARE=/mnt/project-files/leaf-value-gate
BIN_SHA=6eded1e24f9907c4c6ac6870bfea9581d2266ad7cd7bc37c56be6884718698a2
H1_SHA=1e92f2a6b2432cc9a2c67c37a7d30566dcfc7a1d45f0877f5ef697078304563f
first=$((109000016 + 6 * (W - 1)))
case $MODE in
setup)
  mkdir -p "$RUN" "$OUT"
  cd "$REPO" || { echo "STOP: no repo"; exit 2; }
  { cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release -j4 --target one_combat; } > "$BASE/build.log" 2>&1 \
    || { echo "STOP: build failed"; tail -30 "$BASE/build.log"; exit 2; }
  sha=$(sha256sum build/linux-gcc-release/one_combat | cut -d' ' -f1)
  [ "$sha" = "$BIN_SHA" ] || { echo "STOP: binary sha256 $sha != $BIN_SHA"; exit 2; }
  cp build/linux-gcc-release/one_combat "$RUN/"; git rev-parse HEAD > "$RUN/GITSHA"
  cp /mnt/project-files/heart1-ooc-ab-486/heart1.bin "$RUN/"
  h=$(sha256sum "$RUN/heart1.bin" | cut -d' ' -f1)
  [ "$h" = "$H1_SHA" ] || { echo "STOP: heart1.bin sha256 $h != $H1_SHA"; exit 2; }
  seq $first $((first + 5)) > "$OUT/units.txt"
  echo "worker=$W commit=$(cat "$RUN/GITSHA") binary=$sha heart1=$h seeds=$first-$((first + 5))" > "$OUT/FROZEN.txt"
  echo "setup ok: $(cat "$OUT/FROZEN.txt") units $(wc -l < "$OUT/units.txt")"
  ;;
run)
  [ -s "$OUT/FROZEN.txt" ] || { echo "STOP: run setup first"; exit 2; }
  export SIB_EVERY=4 SIB_REPEATS=8 SIB_LONG=4 SIB_DEPTH=2 SIB_LEAVES=256
  # interrupted units (files but no .done) are moved aside and rerun whole
  for s in $(cat "$OUT/units.txt"); do
    b=$OUT/cap-a20-$s
    if [ ! -f "$b.done" ] && compgen -G "$b.*" > /dev/null; then
      ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$b".* "$OUT/aborted-$ts/"
    fi
  done
  xargs -P 4 -I{} bash "$E/run_unit.sh" "$REPO" "$RUN" "$OUT" cap 20 {} 1 < "$OUT/units.txt"
  for s in $(cat "$OUT/units.txt"); do
    [ -f "$OUT/cap-a20-$s.done" ] || { echo "STOP: missing .done for $s"; exit 2; }
    [ -s "$OUT/cap-a20-$s.sib.jsonl" ] || echo "WARN: empty capture for $s"
  done
  cd "$BASE" && tar czf "w$WW.tar.gz" out || { echo "STOP: tar failed"; exit 2; }
  tsha=$(sha256sum "w$WW.tar.gz" | cut -d' ' -f1)
  cp "w$WW.tar.gz" "$SHARE/w$WW.tar.gz" || { echo "STOP: upload failed"; exit 2; }
  { echo "finished=$(date -u +%FT%TZ)"; cat "$OUT/FROZEN.txt"; cat "$OUT"/*.done
    grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null; echo "tar_sha256=$tsha"; } > "$BASE/w$WW.DONE.txt"
  cp "$BASE/w$WW.DONE.txt" "$SHARE/w$WW.DONE.txt" || { echo "STOP: DONE upload failed"; exit 2; }
  echo "run ok tar_sha256=$tsha"
  ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/6"
  grep -L "rc=0" "$OUT"/*.done 2>/dev/null | sed 's/^/not rc=0: /'
  echo "one_combat running: $(pgrep -c -x one_combat)"
  ;;
*) echo "STOP: mode must be setup, run or status"; exit 2 ;;
esac
