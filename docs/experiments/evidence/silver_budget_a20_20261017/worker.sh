#!/usr/bin/env bash
# A20 Silver budget test cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W    build one_combat (build inputs and models must equal CODE_COMMIT), check the binary
#                             hash, copy and check studentc.bin, stage it in $HOME/sbud-wWW, write FROZEN.txt
#   bash worker.sh run W      this worker's seeds in the arms F, L and LP, 4 units at a time, into the local OUT;
#                             when all are done, upload SHARE/wWW.tar.gz and then SHARE/wWW.DONE.txt
#   bash worker.sh status W
# SEEDS lists "LO N"; it is split into NWORKERS contiguous blocks, worker W runs block W.
# Units write to local disk; the share gets two files per worker (the shared folder has a file-count limit).
set -uo pipefail
CMD=${1:-} W=${2:-0}
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/silver_budget_a20_20261017
NWORKERS=$(cat "$D/NWORKERS")
stop() { echo "STOP: $*"; exit 1; }
[[ "$W" =~ ^[1-9][0-9]*$ ]] && [ "$W" -ge 1 ] && [ "$W" -le "$NWORKERS" ] || stop "W must be 1..$NWORKERS, unpadded"
TAG=w$(printf %02d "$W")
SHARE=/mnt/project-files/audit-2026-10-17/silver-budget-a20/runs
WEIGHTS=/mnt/project-files/rollout-student-494/studentc.bin
RUN=$HOME/sbud-$TAG OUT=$HOME/sbud-$TAG/out
EXPECT_BIN=$(cat "$D/binary.sha256")
units() {
  while read -r lo n; do
    [[ "$lo" =~ ^[0-9]+$ ]] || continue
    [ $((n % NWORKERS)) = 0 ] || stop "seed range size $n not divisible by $NWORKERS"
    local k=$((n / NWORKERS)) s
    for s in $(seq $((lo + k*(W-1))) $((lo + k*W - 1))); do echo "F $s"; echo "L $s"; echo "LP $s"; done
  done < "$D/SEEDS"
}
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
  git diff --quiet "$CODE" "$RUNC" -- apps src include CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models \
    docs/experiments/evidence/silver_prior_arch_20261014/models || stop "run commit changes build inputs or models"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  echo "$CODE" > "$RUN/GITSHA"
  want=$(awk '$1=="studentc_bin"{print $2}' "$D/weights.txt")
  cp "$WEIGHTS" "$RUN/studentc.bin" || stop "cannot copy $WEIGHTS"
  got=$(sha256sum "$RUN/studentc.bin" | cut -d' ' -f1)
  [ "$got" = "$want" ] || stop "studentc.bin sha256 $got != $want"
  prior=docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt
  got=$(sha256sum "$prior" | cut -d' ' -f1)
  [ "$got" = "$(awk '$1=="g6_E"{print $2}' "$D/weights.txt")" ] || stop "g6_E sha256 $got"
  python3 tools/analyze_silver_budget_a20.py selftest >/dev/null || stop "analysis selftest"
  units > "$OUT/units.txt" || stop "unit list"
  [ "$(wc -l < "$OUT/units.txt")" -gt 0 ] || stop "no units for W=$W"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PLAN.md "$D"/SEEDS "$D"/NWORKERS "$D"/weights.txt "$RUN"/*.bin "$prior" \
      tools/analyze_silver_budget_a20.py models/v_win_trees.txt; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt"); units $(wc -l < "$OUT/units.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  NUNITS=$(wc -l < "$OUT/units.txt")
  [ "$NUNITS" -gt 0 ] || stop "no units for W=$W"
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  if [ "$n" = "$NUNITS" ]; then
    { echo "finished=$(date -u +%FT%TZ)"; head -1 "$OUT/FROZEN.txt"; cat "$OUT"/*.done; grep -h "bestbench-seed-failure" "$OUT"/*.log "$OUT"/*.err;
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
  grep -h "bestbench-seed-failure" "$OUT"/*.log "$OUT"/*.err 2>/dev/null
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
