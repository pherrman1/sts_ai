#!/usr/bin/env bash
# heart1 card-select capture cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs must equal CODE_COMMIT), check the binary hash, copy and
#                             check the two weight files into $HOME/h1sel-wWW, write FROZEN.txt
#   bash worker.sh run W      this worker's seeds (mode cap), 4 units at a time, into the local OUT; when all are
#                             done, upload SHARE/wWW.tar.gz and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# COHORTS lists "ASC LO N"; each cohort is split into NWORKERS contiguous blocks, worker W runs block W.
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/heart1_select_capture_20261017
NWORKERS=$(cat "$D/NWORKERS")
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[1-9][0-9]*$ ]] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS without leading zeros"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/heart1-select-capture
RUN=$HOME/h1sel-$TAG OUT=$HOME/h1sel-$TAG/out
units() {
  while read -r asc lo n; do
    [[ "$asc" =~ ^[0-9]+$ ]] || continue
    [ $((n % NWORKERS)) = 0 ] || stop "cohort $asc size $n not divisible by $NWORKERS"
    local k=$((n / NWORKERS)) s
    for s in $(seq $((lo + k*(W-1))) $((lo + k*W - 1))); do echo "cap $asc $s"; done
  done < "$D/COHORTS"
}
# units.txt must hold exactly cohort-size/NWORKERS lines per cohort, each "cap ASC SEED" with SEED in its cohort.
check_units() {
  local want=0 asc lo n mode a s
  while read -r asc lo n; do [[ "$asc" =~ ^[0-9]+$ ]] && want=$((want + n / NWORKERS)); done < "$D/COHORTS"
  [ "$want" -gt 0 ] && [ "$(grep -c . "$OUT/units.txt")" = "$want" ] || stop "units.txt must have $want lines"
  while read -r mode a s; do
    [ "$mode" = cap ] || stop "bad unit line: $mode $a $s"
    awk -v a="$a" -v s="$s" '$1==a && s>=$2 && s<$2+$3 {ok=1} END {exit !ok}' "$D/COHORTS" || stop "unit $a $s outside COHORTS"
  done < "$OUT/units.txt"
}
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  [ -s "$D/CODE_COMMIT" ] && [ -s "$D/binary.sha256" ] || stop "run not frozen (CODE_COMMIT, binary.sha256)"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT") EXPECT_BIN=$(cat "$D/binary.sha256")
  git diff --quiet "$CODE" "$RUNC" -- apps src include CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models \
    || stop "run commit changes build inputs or models"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  echo "$CODE" > "$RUN/GITSHA"
  while read -r key want src; do
    f=${key%_bin}.bin
    cp "$src" "$RUN/$f" || stop "cannot copy $src"
    got=$(sha256sum "$RUN/$f" | cut -d' ' -f1)
    [ "$got" = "$want" ] || stop "$f sha256 $got != $want"
  done < "$D/weights.txt"
  units > "$OUT/units.txt" || stop "unit list"
  check_units
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PLAN.md "$D"/COHORTS "$D"/NWORKERS "$D"/weights.txt "$RUN"/*.bin; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt"); units $(wc -l < "$OUT/units.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  check_units
  NUNITS=$(wc -l < "$OUT/units.txt")
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  if [ "$n" = "$NUNITS" ]; then
    { echo "finished=$(date -u +%FT%TZ)"; head -1 "$OUT/FROZEN.txt"; cat "$OUT"/*.done; grep -h "bestbench-seed-failure" "$OUT"/*.log;
      (cd "$OUT" && sha256sum *.csv *.capture.jsonl.gz); } > "$OUT/DONE.txt"
    mkdir -p "$SHARE" || stop "cannot create $SHARE"
    tar -C "$RUN" -czf "$RUN/$TAG.tar.gz" out || stop "tar failed"
    cp "$RUN/$TAG.tar.gz" "$SHARE/$TAG.tar.gz.part" && mv "$SHARE/$TAG.tar.gz.part" "$SHARE/$TAG.tar.gz" || stop "upload failed"
    cmp -s "$RUN/$TAG.tar.gz" "$SHARE/$TAG.tar.gz" || stop "uploaded tar differs (share full?)"
    { cat "$OUT/DONE.txt"; echo "tar_sha256=$(sha256sum "$RUN/$TAG.tar.gz" | cut -d' ' -f1)"; } > "$SHARE/$TAG.DONE.txt"
  fi
  echo "units done: $n/$NUNITS" ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$(wc -l < "$OUT/units.txt")"
  grep -L "rc=0" "$OUT"/*.done 2>/dev/null
  grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
