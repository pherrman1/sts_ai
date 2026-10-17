#!/usr/bin/env bash
# Heart leaf A/B cloud worker (§522). From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs and models must equal CODE_COMMIT), check the binary
#                             hash, copy and check the student C weights, stage them in $HOME/hlab-wWW, write FROZEN.txt
#   bash worker.sh run W      this worker's seeds of every cohort in both arms, 4 units at a time, into the local OUT;
#                             when all are done, upload SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# COHORTS lists "ASC LO N" per ascension; each cohort is split into NWORKERS contiguous blocks, worker W runs block W.
# Units write to local disk; the share gets two files per worker (the shared folder has a file-count limit).
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/heart_leaf_ab_20261017
NWORKERS=$(cat "$D/NWORKERS")
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[1-9][0-9]*$ ]] && [ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS, unpadded (3, never 03)"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/heart-leaf-td/ab
RUN=$HOME/hlab-$TAG OUT=$HOME/hlab-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
WSHARE=/mnt/project-files/heart-leaf-td/ab-weights
units() {
  while read -r asc lo n; do
    [[ "$asc" =~ ^[0-9]+$ ]] || continue
    [ $((n % NWORKERS)) = 0 ] || stop "cohort $asc size $n not divisible by $NWORKERS"
    local k=$((n / NWORKERS)) s
    for s in $(seq $((lo + k*(W-1))) $((lo + k*W - 1))); do echo "C $asc $s"; echo "H $asc $s"; done
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
  for f in studentc; do
    want=$(awk -v k="${f}_bin" '$1==k{print $2}' "$D/weights.txt")
    cp "$WSHARE/$f.bin" "$RUN/$f.bin" || stop "cannot copy $WSHARE/$f.bin"
    got=$(sha256sum "$RUN/$f.bin" | cut -d' ' -f1)
    [ "$got" = "$want" ] || stop "$f.bin sha256 $got != $want"
  done
  sha256sum -c "$D/heart_leaf.sha256" >/dev/null || stop "heart leaf files differ from heart_leaf.sha256"
  python3 tools/analyze_heart_leaf_ab.py selftest >/dev/null || stop "analysis selftest"
  units > "$OUT/units.txt" || stop "unit list"
  [ "$(wc -l < "$OUT/units.txt")" -gt 0 ] || stop "empty unit list"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PLAN.md "$D"/COHORTS "$D"/NWORKERS "$D"/weights.txt "$RUN"/*.bin \
      tools/analyze_heart_leaf_ab.py models/v_win_trees.txt models/candidates/v_win_x2b_public_trees.txt models/candidates/heart_leaf_td2/*; } > "$OUT/FROZEN.txt"
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
