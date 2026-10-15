#!/usr/bin/env bash
# §479 cloud worker W (1..NWORKERS). From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs must equal code commit 7a413622), check the binary hash
#   bash worker.sh run W      run.sh on this worker's 8 seeds (105000000 + 8(W-1) .., 4 shards x 2 seeds, 6 h
#                             per-shard timeout) into $HOME/x479-wWW/out; when all 4 shards end with rc=0, upload
#                             SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
E=docs/experiments/evidence/silver_rollout_policy_2x2_20261014
NWORKERS=$(cat "$E/NWORKERS")
CODE=7a413622b47f91e11b7ae12e749fc27502948619
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[0-9]+$ ]] && [ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/silver-rollout-2x2
TOP=$HOME/x479-$TAG OUT=$HOME/x479-$TAG/out
BASE=$((105000000 + 8 * (W - 1)))
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
  echo "setup ok: worker=$W run=$(git rev-parse HEAD) code=$CODE binary=$got seeds=$BASE..$((BASE + 7))" | tee "$TOP/SETUP.txt" ;;
run)
  [ -f "$TOP/SETUP.txt" ] || stop "run setup first"
  if [ -d "$OUT" ] && [ ! -f "$OUT/DONE.txt" ]; then mv "$OUT" "$TOP/aborted-$(date -u +%Y%m%dT%H%M%SZ)"; fi
  [ -f "$OUT/DONE.txt" ] || bash "$E/run.sh" "$OUT" 8 "$BASE" "0 1 2 3" 6h
  [ -f "$OUT/DONE.txt" ] || stop "not every shard ended with rc=0: $(tr '\n' ';' < "$OUT/shards.txt" 2>/dev/null)"
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
