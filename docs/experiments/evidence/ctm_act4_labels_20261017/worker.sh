#!/usr/bin/env bash
# Act-4 CTM label collection worker (Philipp 2026-10-17 16:18Z "run full act 4 label colleciton").
# Run from the repo checkout at the run commit; this script is part of that commit.
#   bash worker.sh setup W N   check the checkout, build one_combat, check its sha256, stage the teacher
#   bash worker.sh run W N     this worker's units, 4 at a time, into local OUT; then upload SHARE/wWW.tar.gz + wWW.DONE.txt
#   bash worker.sh status W N
# N workers split seeds 111160000..111169999 evenly (N divides 10000 into multiples of 25); worker W = 1..N gets
# 111160000 + (W-1)*10000/N .. +10000/N-1 in units of 25 seeds. W = 0 is the smoke: one unit, seeds 111157000..003.
set -uo pipefail
CMD=${1:-} W=${2:-x} N=${3:-x}
[[ "$N" =~ ^[0-9]+$ ]] && [ "$N" -ge 1 ] && [ $((10000 % N)) = 0 ] && [ $(((10000 / N) % 25)) = 0 ] || { echo "STOP: bad N"; exit 1; }
[[ "$W" =~ ^[0-9]+$ ]] && [ "$W" -le "$N" ] || { echo "STOP: W must be 0..N"; exit 1; }
TAG=w$(printf %02d "$W")
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
SHARE=/mnt/project-files/ctm-a20/act4-labels
RUN=$HOME/ctmact4-$TAG OUT=$HOME/ctmact4-$TAG/out
CODE=79263192c3025402861c274ffaec9395e5c0df33
EXPECT_BIN=5e88ec0aa4216cd001d5bb9849dcd42861501d79f9e8f082320e6e9e8e49279a
stop() { echo "STOP: $*"; exit 1; }
units() {
  if [ "$W" = 0 ]; then echo "act4 111157000 4"; return; fi
  local per=$((10000 / N)) lo=$((111160000 + (W - 1) * 10000 / N))
  for ((k = 0; k < per; k += 25)); do echo "act4 $((lo + k)) 25"; done; }
cd "$REPO" || stop "no repo at $REPO"
case $CMD in
setup)
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  git diff --quiet "$CODE" HEAD -- apps src include bindings cmake CMakeLists.txt CMakePresets.json selfplay models extern json pybind11 \
    || stop "checkout code differs from $CODE"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  cp "$HERE/teacher.json" "$RUN/teacher.json"
  python3 -c "import json,sys;t=json.load(open(sys.argv[1]));assert t['git_sha']==sys.argv[2] and t['environment']['STS_EXECUTABLE_GIT_SHA']==sys.argv[2]" \
    "$RUN/teacher.json" "$CODE" || stop "teacher does not match the code commit"
  { echo "worker=$W of $N run=$(git rev-parse HEAD) code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1) host=$(hostname)/$(cat /proc/sys/kernel/random/boot_id)"
    sha256sum "$HERE"/*.sh "$HERE"/teacher.json; } > "$OUT/FROZEN.txt"
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
    echo "WORKER_OK $TAG units=$n rows=$(cat "$OUT"/*.jsonl | wc -l)"
  else echo "units done: $n/$NU (rerun 'run' to resume)"; fi ;;
status)
  echo "units done: $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$(units | wc -l) rows=$(cat "$OUT"/*.jsonl 2>/dev/null | wc -l)" ;;
*) stop "usage: worker.sh setup|run|status W N" ;;
esac
