#!/usr/bin/env bash
# §464 cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs and models must equal CODE_COMMIT), check the binary
#                             hash, stage it in $HOME/x464-wWW, write OUT/FROZEN.txt
#   bash worker.sh run W      this worker's 8 seeds in both arms (16 one-seed units), 4 at a time, into the local
#                             OUT; when all 16 are done, upload SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# W = 1..NPAIRS/8; worker W runs seeds 93000000+8(W-1) .. +7 in the arms `combo` and `rulesmerge`.
# Units write to local disk; the share gets two files per worker (the shared folder has a file-count limit).
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ooc_tree_rules_464_20261014
NPAIRS=$(cat "$D/NPAIRS") NWORKERS=$(( $(cat "$D/NPAIRS") / 8 ))
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[0-9]+$ ]] && [ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/ooc-tree-rules-464
RUN=$HOME/x464-$TAG OUT=$HOME/x464-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
LO=$((93000000 + 8*(W-1)))
NUNITS=16
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
  python3 tools/analyze_ooc_tree_rules_464.py selftest >/dev/null || stop "analysis selftest"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PREREG.md "$D"/NPAIRS tools/analyze_ooc_tree_rules_464.py models/v_rich_trees.txt \
      models/candidates/v_win_x2b_public_trees.txt; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  for k in $(seq 0 7); do echo "combo $((LO+k)) 1"; echo "rulesmerge $((LO+k)) 1"; done > "$OUT/units.txt"
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  if [ "$n" = $NUNITS ]; then
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
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$NUNITS"; cat "$OUT"/*.done 2>/dev/null
  grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
