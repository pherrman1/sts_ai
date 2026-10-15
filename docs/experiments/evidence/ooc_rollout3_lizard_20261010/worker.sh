#!/usr/bin/env bash
# §423 cloud worker. From a clean checkout of the run commit:
#   bash worker.sh setup W     build one_combat (build inputs must equal CODE_COMMIT apart from the candidate
#                              model), check binary, candidate model and manifest hashes, stage the binary in
#                              $HOME/r3liz-wWW, write OUT/FROZEN.txt
#   bash worker.sh run W       this worker's 8 one-seed `lizard` units, 4 at a time -> OUT/DONE.txt (blocks)
#   bash worker.sh status W
# W = 1..16; worker W runs seeds 70000000+8(W-1) .. +7 (the §422 cohort block W-1).
set -uo pipefail
CMD=${1:-} W=${2:-0}
[[ "$W" =~ ^([1-9]|1[0-6])$ ]] || { echo "STOP: W must be 1..16"; exit 1; }
WW=$(printf %02d "$W")
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ooc_rollout3_lizard_20261010
MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native
SHARE=/mnt/project-files/ooc-rollout3-lizard
OUT=$SHARE/w$WW RUN=$HOME/r3liz-w$WW
EXPECT_BIN=$(cat "$D/binary.sha256")
EXPECT_MODEL=c6d56bbc959f4d5de8fe1dd57f58a922112cd8323bcbac9711e0aecda93f5a3c
EXPECT_MANIFEST=64da17762b08114f28ae4d182fddde82da917951f4717bb95d352c42bc4a933e
stop() { echo "STOP: $*"; exit 1; }
LO=$((70000000 + 8*(W-1)))
NUNITS=8
case $CMD in
setup)
  case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files (noexec)";; esac
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
  git diff --quiet "$CODE" "$RUNC" -- apps src include CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models \
    ":(exclude)$MODEL" || stop "run commit changes build inputs or models"
  [ "$(sha256sum "$MODEL" | cut -d' ' -f1)" = "$EXPECT_MODEL" ] || stop "candidate model sha256"
  [ "$(sha256sum "$D/candidate-v3-lizard.json" | cut -d' ' -f1)" = "$EXPECT_MANIFEST" ] || stop "candidate manifest sha256"
  git submodule update --init --recursive >/dev/null || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null \
    || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  got=$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)
  [ "$got" = "$EXPECT_BIN" ] || stop "binary sha256 $got != $EXPECT_BIN ($(g++ --version | head -1))"
  echo "$CODE" > "$RUN/GITSHA"
  python3 tools/analyze_rollout3_lizard.py selftest >/dev/null || stop "analysis selftest"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN model=$EXPECT_MODEL $(g++ --version | head -1)"
    sha256sum "$D"/*.sh "$D"/PREREG.md "$D"/candidate-v3-lizard.json tools/analyze_rollout3_lizard.py; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(head -1 "$OUT/FROZEN.txt")" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  for k in 0 1 2 3 4 5 6 7; do echo "lizard $((LO+k)) 1"; done > "$OUT/units.txt"
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  [ "$n" = $NUNITS ] && { echo "finished=$(date -u +%FT%TZ)"; cat "$OUT"/*.done; grep -h "bestbench-seed-failure" "$OUT"/*.log;
    sha256sum "$OUT"/*.csv; } > "$OUT/DONE.txt"
  echo "units done: $n/$NUNITS" ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/$NUNITS"; cat "$OUT"/*.done 2>/dev/null
  grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null
  echo "running: $(pgrep -x one_combat | wc -l)" ;;
*) stop "unknown command $CMD" ;;
esac
