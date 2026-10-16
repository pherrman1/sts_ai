#!/usr/bin/env bash
# 64-rollout sibling-leaf capture cloud worker.  usage: worker.sh setup|run|status W   (W = 1..32, unpadded)
# Worker W runs A20 seeds 110000000+2(W-1) and +1, both at once, then uploads
# /mnt/project-files/leaf-value-64/wWW.tar.gz and wWW.DONE.txt.
set -uo pipefail
MODE=${1:-}; W=${2:-}
case $W in [1-9]|[12][0-9]|3[0-2]) ;; *) echo "STOP: W must be 1..32 (unpadded)"; exit 2 ;; esac
WW=$(printf %02d "$W")
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
UNIT=$REPO/docs/experiments/evidence/ooc_sibling_leaf_capture_20261015/run_unit.sh
BASE=$HOME/sib64-w$WW; RUN=$BASE/run; OUT=$BASE/out; SHARE=/mnt/project-files/leaf-value-64
BIN_SHA=992f5cdc3a320554f85c034daea69338481184a35322e946bb3b02211336e0b6
H1_SHA=1e92f2a6b2432cc9a2c67c37a7d30566dcfc7a1d45f0877f5ef697078304563f
N=2
first=$((110000000 + N * (W - 1)))
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
  seq $first $((first + N - 1)) > "$OUT/units.txt"
  echo "worker=$W commit=$(cat "$RUN/GITSHA") binary=$sha heart1=$h seeds=$first-$((first + N - 1))" > "$OUT/FROZEN.txt"
  echo "setup ok: $(cat "$OUT/FROZEN.txt") units $(wc -l < "$OUT/units.txt")"
  ;;
run)
  [ -s "$OUT/FROZEN.txt" ] || { echo "STOP: run setup first"; exit 2; }
  export SIB_EVERY=2 SIB_REPEATS=64 SIB_LONG=0 SIB_DEPTH=2 SIB_LEAVES=128
  # interrupted units (files but no .done) are moved aside and rerun whole
  for s in $(cat "$OUT/units.txt"); do
    b=$OUT/cap-a20-$s
    if [ ! -f "$b.done" ] && compgen -G "$b.*" > /dev/null; then
      ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$b".* "$OUT/aborted-$ts/"
    fi
  done
  xargs -P $N -I{} bash "$UNIT" "$REPO" "$RUN" "$OUT" cap 20 {} 1 < "$OUT/units.txt" \
    || { echo "STOP: unit dispatcher failed"; exit 2; }
  for s in $(cat "$OUT/units.txt"); do
    [ -f "$OUT/cap-a20-$s.done" ] || { echo "STOP: missing .done for $s"; exit 2; }
    grep -Eq '^tag=[^ ]+ rc=0( |$)' "$OUT/cap-a20-$s.done" || { echo "STOP: failed unit $s"; exit 2; }
    [ -s "$OUT/cap-a20-$s.sib.jsonl" ] || { echo "STOP: empty capture for $s"; exit 2; }
  done
  cd "$BASE" && tar czf "w$WW.tar.gz" out || { echo "STOP: tar failed"; exit 2; }
  tsha=$(sha256sum "w$WW.tar.gz" | cut -d' ' -f1)
  mkdir -p "$SHARE" && cp "w$WW.tar.gz" "$SHARE/w$WW.tar.gz" || { echo "STOP: upload failed"; exit 2; }
  { echo "finished=$(date -u +%FT%TZ)"; cat "$OUT/FROZEN.txt"; cat "$OUT"/*.done
    grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null; echo "tar_sha256=$tsha"; } > "$BASE/w$WW.DONE.txt"
  cp "$BASE/w$WW.DONE.txt" "$SHARE/w$WW.DONE.txt" || { echo "STOP: DONE upload failed"; exit 2; }
  echo "run ok tar_sha256=$tsha"
  ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$N"
  grep -L "rc=0" "$OUT"/*.done 2>/dev/null | sed 's/^/not rc=0: /'
  echo "one_combat running: $(pgrep -c -x one_combat)"
  ;;
*) echo "STOP: mode must be setup, run or status"; exit 2 ;;
esac
