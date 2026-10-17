#!/usr/bin/env bash
# Per-type Silver potion weight A/B cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs and models must equal CODE_COMMIT), check the binary
#                             hash, stage it in $HOME/xpw-wWW, write OUT/FROZEN.txt
#   bash worker.sh run W      this worker's units (all three arms of its seeds), 4 at a time, into the local OUT; when all
#                             are done, upload SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# Cohort (COHORT file: count N): A20 seeds 111152000 .. +N-1, all three arms; seed i goes to worker (i mod NWORKERS) + 1.
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/silver_potion_weights_20261017
NWORKERS=$(cat "$D/NWORKERS"); N=$(cat "$D/COHORT")
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[0-9]+$ ]] && [ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/silver-potion-weights
RUN=$HOME/xpw-$TAG OUT=$HOME/xpw-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
units() {
  local i=0 s
  for s in $(seq 111152000 $((111152000 + N - 1))); do
    [ $((i % NWORKERS + 1)) = "$W" ] && { echo "base $s"; echo "level $s"; echo "type $s"; }; i=$((i + 1)); done
}
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
  git diff --quiet "$CODE" "$RUNC" -- apps src include CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models \
    || stop "run commit changes build inputs or models"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build build/linux-gcc-release --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  echo "$CODE" > "$RUN/GITSHA"
  want=$(awk '$1=="studentc_bin"{print $2}' "$D/weights.txt")
  cp /mnt/project-files/rollout-student-494/studentc.bin "$RUN/studentc.bin" || stop "cannot copy studentc.bin"
  got=$(sha256sum "$RUN/studentc.bin" | cut -d' ' -f1)
  [ "$got" = "$want" ] || stop "studentc.bin sha256 $got != $want"
  python3 tools/analyze_silver_potion_weights.py selftest >/dev/null || stop "analysis selftest"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PREREG.md "$D"/NWORKERS "$D"/COHORT "$D"/WEIGHTS_TYPE "$D"/weights.txt "$RUN/studentc.bin" tools/analyze_silver_potion_weights.py; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  units > "$OUT/units.txt"
  NUNITS=$(wc -l < "$OUT/units.txt")
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  if [ "$n" = "$NUNITS" ]; then
    { echo "finished=$(date -u +%FT%TZ)"; head -1 "$OUT/FROZEN.txt"; cat "$OUT"/*.done; grep -h "bestbench-seed-failure" "$OUT"/*.log;
      (cd "$OUT" && sha256sum *.csv); } > "$OUT/DONE.txt"
    mkdir -p "$SHARE" || stop "cannot create $SHARE"
    tar -C "$RUN" -cf "$RUN/$TAG.tar" out || stop "tar failed"
    cp "$RUN/$TAG.tar" "$SHARE/$TAG.tar.part" && mv "$SHARE/$TAG.tar.part" "$SHARE/$TAG.tar" || stop "upload failed"
    cmp -s "$RUN/$TAG.tar" "$SHARE/$TAG.tar" || stop "uploaded tar differs (share full?)"
    { cat "$OUT/DONE.txt"; echo "tar_sha256=$(sha256sum "$RUN/$TAG.tar" | cut -d' ' -f1)"; } > "$SHARE/$TAG.DONE.txt"
  fi
  echo "units done: $n/$NUNITS" ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$(wc -l < "$OUT/units.txt" 2>/dev/null)"; cat "$OUT"/*.done 2>/dev/null
  grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
