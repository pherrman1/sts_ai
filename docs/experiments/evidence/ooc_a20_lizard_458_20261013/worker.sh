#!/usr/bin/env bash
# §458 cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat from a detached checkout of CODE_COMMIT (the §457 code; main has moved),
#                             check the binary hash, return to the run commit, stage it in $HOME/a458-wWW, write OUT/FROZEN.txt
#   bash worker.sh run W      this worker's 8 seeds in the arm combo_liz (8 one-seed units at ascension 20), 4 at a time,
#                             into the local OUT; when all 48 are done, upload SHARE/wWW.tar and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# W = 1..NPAIRS/8 (16 workers, Philipp's card); worker W runs seeds 87000000+8(W-1) .. +7 in the arm `combo_liz`
# (off/combo_def: §457 rows).
# Units write to local disk; the share gets two files per worker (the shared folder has a file-count limit).
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ooc_a20_lizard_458_20261013
PER=8 NPAIRS=$(cat "$D/NPAIRS") NWORKERS=$(( $(cat "$D/NPAIRS") / 8 ))
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[0-9]+$ ]] && [ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/ooc-a20-lizard
RUN=$HOME/a458-$TAG OUT=$HOME/a458-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
LO=$((87000000 + PER*(W-1)))
NUNITS=$PER
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
  # main moved past the §457 code (#520 changed apps/src): build at CODE, then return to the run commit
  git diff --quiet "$CODE" "$RUNC" -- json pybind11 models selfplay/models || stop "run commit changes submodules or models"
  git checkout -q --detach "$CODE" && git submodule update --init --recursive >/dev/null || stop "checkout $CODE"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || { git checkout -q --detach "$RUNC"; stop "build failed"; }
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  git checkout -q --detach "$RUNC" && git submodule update --init --recursive >/dev/null || stop "return to $RUNC"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  echo "$CODE" > "$RUN/GITSHA"
  # A20 Lizard CTM (combo_liz): copy fast/standard/manifest from the pinned data-branch commit, check each sha256
  DATAC=$(awk '$1=="data_commit"{print $2}' "$D/ctm_artifacts.txt")
  git fetch -q origin claude/ctm-a20-data || stop "cannot fetch claude/ctm-a20-data"
  git cat-file -e "$DATAC^{commit}" || stop "data commit $DATAC not found"
  mkdir -p "$RUN/ctm"
  for role in fast standard manifest; do
    read -r _ path sha < <(awk -v r=$role '$1==r' "$D/ctm_artifacts.txt")
    [ -n "$path" ] && [ -n "$sha" ] || stop "ctm_artifacts.txt lacks $role"
    ext=native; [ $role = manifest ] && ext=json
    git show "$DATAC:$path" > "$RUN/ctm/$role.$ext" || stop "cannot read $path at $DATAC"
    got=$(sha256sum "$RUN/ctm/$role.$ext" | cut -d' ' -f1)
    [ "$got" = "$sha" ] || stop "$role sha256 $got != $sha"
  done
  python3 tools/analyze_ooc_a20_458.py selftest >/dev/null || stop "analysis selftest"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PREREG.md "$D"/NPAIRS "$D"/ctm_artifacts.txt "$RUN"/ctm/* tools/analyze_ooc_a20_458.py models/v_win_trees.txt; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  for k in $(seq 0 $((PER-1))); do echo "combo_liz $((LO+k)) 1"; done > "$OUT/units.txt"
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
