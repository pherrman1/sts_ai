#!/usr/bin/env bash
# §443 Stage 4 fresh A20 gate corpus worker (PREREG ctm-a20/regate/PREREG-REGATE.md). Copy this folder's scripts to
# $HOME/ctm443s4 first (the share is noexec). Same run commit, binary, teacher and run_unit.sh as Stage 1; only seeds differ.
#   bash worker.sh setup W   check the checkout is the run commit, build one_combat, check its sha256, stage the teacher
#   bash worker.sh run W     this worker's units, 4 at a time, into local OUT; then upload SHARE/wWW.tar.gz + wWW.DONE.txt
#   bash worker.sh status W
# W = 1..8: main gate seeds 78600000+500(W-1) .. +499 in 10 units of 50, plus one Lizard diagnostic unit of 50:
#        odd W lizard_fairy 78610000+50*((W-1)/2), even W lizard_brew 78611000+50*(W/2-1).
# W = 0: smoke, one seed per unit: main 78009060, 78009061, lizard_fairy 78009062, lizard_brew 78009063.
set -uo pipefail
CMD=${1:-} W=${2:-x}
[[ "$W" =~ ^[0-8]$ ]] || { echo "STOP: W must be 0..8"; exit 1; }
TAG=w$(printf %02d "$W")
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO=/home/user/sts_ai
SHARE=/mnt/project-files/ctm-a20/stage4
RUN=$HOME/ctm443s4-$TAG OUT=$HOME/ctm443s4-$TAG/out
RUNC=90f6df64c87ad9b298e06d1a19bb4e69fc577296
EXPECT_BIN=12e881be13ee6b7df0fd6d6810cb8e6cc34dd54c82cc842e6a889c16e27cc05b
stop() { echo "STOP: $*"; exit 1; }
units() {
  if [ "$W" = 0 ]; then
    printf '%s\n' "main 78009060 1 none" "main 78009061 1 none" "lizard_fairy 78009062 1 lizard_fairy" "lizard_brew 78009063 1 lizard_brew"
  else
    LO=$((78600000 + 500*(W-1))); for ((k=0;k<500;k+=50)); do echo "main $((LO+k)) 50 none"; done
    if [ $((W % 2)) = 1 ]; then echo "lizard_fairy $((78610000 + 50*((W-1)/2))) 50 lizard_fairy"
    else echo "lizard_brew $((78611000 + 50*(W/2-1))) 50 lizard_brew"; fi
  fi; }
cd "$REPO" || stop "no repo at $REPO"
case $CMD in
setup)
  [ "$(git rev-parse HEAD)" = "$RUNC" ] || stop "checkout is not the run commit $RUNC"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  cp "$HERE/teacher.json" "$RUN/teacher.json"
  python3 -c "import json,sys;t=json.load(open(sys.argv[1]));assert t['git_sha']==sys.argv[2] and t['executable_sha256']==sys.argv[3]" \
    "$RUN/teacher.json" "$RUNC" "$EXPECT_BIN" || stop "teacher does not match run commit/binary"
  { echo "worker=$W run=$RUNC binary=$EXPECT_BIN $(g++ --version | head -1)"; sha256sum "$HERE"/*.sh "$HERE"/teacher.json; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  units > "$OUT/units.txt"; NU=$(wc -l < "$OUT/units.txt")
  xargs -P 4 -L 1 bash "$HERE/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  if [ "$n" = "$NU" ]; then
    { echo "finished=$(date -u +%FT%TZ)"; head -1 "$OUT/FROZEN.txt"; cat "$OUT"/*.done; } > "$OUT/DONE.txt"
    mkdir -p "$SHARE" || stop "cannot create $SHARE"
    tar -C "$RUN" -czf "$RUN/$TAG.tar.gz" out || stop "tar failed"
    cp "$RUN/$TAG.tar.gz" "$SHARE/$TAG.tar.gz.part" && mv "$SHARE/$TAG.tar.gz.part" "$SHARE/$TAG.tar.gz" || stop "upload failed"
    cmp -s "$RUN/$TAG.tar.gz" "$SHARE/$TAG.tar.gz" || stop "uploaded tar differs (share full?)"
    { cat "$OUT/DONE.txt"; echo "tar_sha256=$(sha256sum "$RUN/$TAG.tar.gz" | cut -d' ' -f1)"; } > "$SHARE/$TAG.DONE.txt"
  fi
  echo "units done: $n/$NU" ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$(units | wc -l)"; grep -L "rc=0" "$OUT"/*.done 2>/dev/null
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
