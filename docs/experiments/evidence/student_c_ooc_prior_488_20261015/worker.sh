#!/usr/bin/env bash
# §488 cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs and models must equal CODE_COMMIT), check the binary
#                             hash, copy and check the student C weights, stage both in $HOME/a488-wWW, write FROZEN.txt
#   bash worker.sh run W      this worker's seeds of every cohort in both arms, 4 units at a time, into the local OUT;
#                             when all are done, upload SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# COHORTS lists "ASC LO N" per ascension; each cohort is split into NWORKERS contiguous blocks, worker W runs block W.
# Units write to local disk; the share gets two files per worker (the shared folder has a file-count limit).
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/student_c_ooc_prior_488_20261015
NWORKERS=$(cat "$D/NWORKERS")
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[0-9]+$ ]] || stop "W must be 1..$NWORKERS"
W=$((10#$W))                                       # a zero-padded W (09) is not read as octal
[ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/student-c-488
RUN=$HOME/a488-$TAG OUT=$HOME/a488-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
EXPECT_W=$(awk '$1=="studentc_bin"{print $2}' "$D/student_weights.txt")
units() {
  while read -r asc lo n; do
    [[ "$asc" =~ ^[0-9]+$ ]] || continue
    [ $((n % NWORKERS)) = 0 ] || stop "cohort $asc size $n not divisible by $NWORKERS"
    local k=$((n / NWORKERS)) s
    for s in $(seq $((lo + k*(W-1))) $((lo + k*W - 1))); do echo "studentc $asc $s"; echo "v4 $asc $s"; done
  done < "$D/COHORTS"
}
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
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
  cp "$SHARE/studentc.bin" "$RUN/studentc.bin" || stop "cannot copy $SHARE/studentc.bin"
  got=$(sha256sum "$RUN/studentc.bin" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_W" ] || stop "studentc.bin sha256 $got != $EXPECT_W"
  python3 tools/analyze_student_prior_488.py selftest >/dev/null || stop "analysis selftest"
  units > "$OUT/units.txt" || stop "unit list"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN studentc=$EXPECT_W $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PREREG.md "$D"/COHORTS "$D"/NWORKERS "$D"/student_weights.txt "$RUN/studentc.bin" \
      tools/analyze_student_prior_488.py models/v_win_trees.txt; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt"); units $(wc -l < "$OUT/units.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  NUNITS=$(wc -l < "$OUT/units.txt")
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  if [ "$n" = "$NUNITS" ]; then
    { echo "finished=$(date -u +%FT%TZ)"; head -1 "$OUT/FROZEN.txt"; cat "$OUT"/*.done; grep -h "bestbench-seed-failure" "$OUT"/*.log;
      (cd "$OUT" && sha256sum *.csv); } > "$OUT/DONE.txt"
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
