#!/usr/bin/env bash
# §427–§430 cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup ARM W   build one_combat (build inputs and the models these arms load must equal
#                                CODE_COMMIT), check the binary hash, stage it in $HOME/r3v-ARM-wWW, write OUT/FROZEN.txt
#   bash worker.sh run ARM W     this worker's 16 one-seed ARM units, 4 at a time, into the local OUT; when all 16
#                                are done, upload SHARE/ARM-wWW.tar and then SHARE/ARM-wWW.DONE.txt (blocks)
#   bash worker.sh status ARM W
# ARM = s4096 | wnarrow | wbroad | r5; W = 1..8; worker W runs seeds 70000000+16(W-1) .. +15 (§422 cohort).
# Units write to local disk; the share gets two files per worker (the shared folder has a file-count limit).
set -uo pipefail
CMD=${1:-} ARM=${2:-} W=${3:-0}
case $ARM in s4096|wnarrow|wbroad|r5) ;; *) echo "STOP: ARM must be s4096, wnarrow, wbroad or r5"; exit 1 ;; esac
[[ "$W" =~ ^[1-8]$ ]] || { echo "STOP: W must be 1..8"; exit 1; }
WW=$(printf %02d "$W") TAG=$ARM-w$(printf %02d "$W")
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ooc_rollout3_variants_20261011
SHARE=/mnt/project-files/ooc-rollout3-variants
RUN=$HOME/r3v-$TAG OUT=$HOME/r3v-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
stop() { echo "STOP: $*"; exit 1; }
LO=$((70000000 + 16*(W-1)))
NUNITS=16
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
  git diff --quiet "$CODE" "$RUNC" -- apps src include CMakeLists.txt CMakePresets.json json pybind11 models \
    selfplay/models/combat_transition_deepsets_pathb_r2.native selfplay/models/combat_transition_near_full_escape_pathb_r2.native \
    selfplay/models/ooc_strategic_tok_final.native || stop "run commit changes build inputs or models"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  echo "$CODE" > "$RUN/GITSHA"
  python3 tools/analyze_rollout3_variants.py selftest >/dev/null || stop "analysis selftest"
  { echo "arm=$ARM worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PREREG.md tools/analyze_rollout3_variants.py; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  for k in $(seq 0 15); do echo "$ARM $((LO+k)) 1"; done > "$OUT/units.txt"
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
