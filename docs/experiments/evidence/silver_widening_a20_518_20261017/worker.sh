#!/usr/bin/env bash
# §518 widening run, cloud worker W (1..NWORKERS). From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs must equal CODE_COMMIT), check the binary hash
#   bash worker.sh run W      run.sh on this worker's PER_WORKER seeds (BASE_SEED + PER_WORKER(W-1) ..,
#                             4 shards, 8 h per-shard timeout) into $HOME/x518-wWW/out; when all 4 shards end
#                             with rc=0, upload SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
E=docs/experiments/evidence/silver_widening_a20_518_20261017
NWORKERS=$(cat "$E/NWORKERS"); PER_WORKER=$(cat "$E/PER_WORKER"); BASE_SEED=$(cat "$E/BASE_SEED")
CODE=$(cat "$E/CODE_COMMIT")
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[1-9][0-9]*$ ]] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS, unpadded (got '$W')"
(( PER_WORKER > 0 && PER_WORKER % 4 == 0 )) || stop "PER_WORKER must be a positive multiple of 4"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/silver-widening-518
TOP=$HOME/x518-$TAG OUT=$HOME/x518-$TAG/out
BASE=$((BASE_SEED + PER_WORKER * (W - 1)))
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  git diff --quiet "$CODE" HEAD -- apps src include CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models \
    || stop "run commit changes build inputs or models"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build build/linux-gcc-release --target one_combat -j4 >/dev/null \
    || stop "build failed"
  got=$(sha256sum build/linux-gcc-release/one_combat | cut -d' ' -f1)
  [ "$got" = "$(cat "$E/BINARY_SHA256")" ] || stop "binary sha256 $got != $(cat "$E/BINARY_SHA256") ($(g++ --version | head -1))"
  mkdir -p "$TOP"
  echo "setup ok: worker=$W run=$(git rev-parse HEAD) code=$CODE binary=$got seeds=$BASE..$((BASE + PER_WORKER - 1))" | tee "$TOP/SETUP.txt" ;;
run)
  [ -f "$TOP/SETUP.txt" ] || stop "run setup first"
  if [ -d "$OUT" ] && [ ! -f "$OUT/DONE.txt" ]; then mv "$OUT" "$TOP/aborted-$(date -u +%Y%m%dT%H%M%SZ)"; fi
  [ -f "$OUT/DONE.txt" ] || bash "$E/run.sh" "$OUT" "$PER_WORKER" "$BASE" "0 1 2 3" 8h
  [ -f "$OUT/DONE.txt" ] || stop "not every shard ended with rc=0: $(tr '\n' ';' < "$OUT/shards.txt" 2>/dev/null)"
  for i in 0 1 2 3; do
    [ "$(wc -l < "$OUT/shard$i.arms.csv" 2>/dev/null || echo 0)" -ge 2 ] || stop "shard$i wrote no arm rows"
  done
  { echo "finished=$(date -u +%FT%TZ) worker=$W"; head -1 "$OUT/FROZEN.txt"; cat "$OUT/shards.txt"
    (cd "$OUT" && sha256sum *.csv); } > "$TOP/DONE.txt"
  mkdir -p "$SHARE" || stop "cannot create $SHARE"
  tar -C "$TOP" -cf "$TOP/$TAG.tar" out || stop "tar failed"
  cp "$TOP/$TAG.tar" "$SHARE/$TAG.tar.part" && mv "$SHARE/$TAG.tar.part" "$SHARE/$TAG.tar" || stop "upload failed"
  cmp -s "$TOP/$TAG.tar" "$SHARE/$TAG.tar" || stop "uploaded tar differs (share full?)"
  { cat "$TOP/DONE.txt"; echo "tar_sha256=$(sha256sum "$TOP/$TAG.tar" | cut -d' ' -f1)"; } > "$SHARE/$TAG.DONE.txt"
  echo "uploaded $TAG.tar OK" ;;
status)
  cat "$OUT/shards.txt" 2>/dev/null; wc -l "$OUT"/shard*.arms.csv 2>/dev/null | tail -n 5
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
