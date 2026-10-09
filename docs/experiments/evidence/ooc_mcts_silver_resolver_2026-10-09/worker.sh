#!/usr/bin/env bash
# §410 cloud worker. From a clean checkout of the frozen commit:
#   bash worker.sh setup W        build one_combat at CODE_COMMIT, check hashes, stage inputs in $HOME/silvres-wWW,
#                                 return to the run commit
#   bash worker.sh smoke W        (worker 1 only) one seed per arm, banner checks -> OUT/SMOKE_PASS|SMOKE_FAIL
#   bash worker.sh run W          this worker's 16 units, 4 at a time -> OUT/DONE.txt
#   bash worker.sh status W
set -uo pipefail
CMD=$1 W=$2 WW=$(printf %02d "$2")
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
D=docs/experiments/evidence/ooc_mcts_silver_resolver_2026-10-09
SHARE=/mnt/project-files/ooc-mcts-silver-resolver
OUT=$SHARE/w$WW RUN=$HOME/silvres-w$WW
EXPECT_BIN=$(cat "$D/binary.sha256")
stop() { echo "STOP: $*"; exit 1; }
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || stop "sha256 mismatch: $1"; }
blocks() { for b in $((W-1)) $((W+3)) $((W+7)) $((W+11)); do echo $((64000000 + 8*b)); done; }
case $CMD in
setup)
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  RUNC=$(git rev-parse HEAD) CODE=$(cat "$D/CODE_COMMIT")
  git diff --quiet "$CODE" "$RUNC" -- apps src include CMakeLists.txt CMakePresets.json || stop "run commit changes build inputs"
  git checkout -q --detach "$CODE" && git submodule update --init --recursive >/dev/null || stop "checkout $CODE"
  cmake --preset linux-gcc-release >/dev/null && cmake --build build/linux-gcc-release --target one_combat -j4 >/dev/null || stop "build failed"
  mkdir -p "$RUN" "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  git checkout -q --detach "$RUNC" && git submodule update --init --recursive >/dev/null || stop "checkout $RUNC"
  check "$RUN/one_combat" "$EXPECT_BIN"
  cp /mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/prior-natpert.compact.txt "$RUN/"
  check "$RUN/prior-natpert.compact.txt" 573305c48076c135f791d0712efb03be7e620aeeb961e962700ce2c60188c6ee
  echo "$CODE" > "$RUN/GITSHA"
  grep -q "__SILVCPU_SIMS__" "$D/arm_env.sh" && stop "arm_env.sh not frozen"
  python3 tools/analyze_silver_resolver_pilot.py selftest || stop "analysis selftest"
  { echo "worker=$W run=$RUNC code=$CODE binary=$EXPECT_BIN $(g++ --version | head -1)"
    sha256sum "$D"/*.sh tools/analyze_silver_resolver_pilot.py; } > "$OUT/FROZEN.txt"
  echo "setup ok: $(cat "$OUT/FROZEN.txt" | head -1)" ;;
smoke)
  [ "$W" = 1 ] || stop "smoke is worker 1 only"
  S=$SHARE/smoke; mkdir -p "$S"
  for arm in silvcpu prod off silv2048; do bash "$D/run_unit.sh" "$REPO" "$RUN" "$S" $arm 64009001 1; done
  ok=1
  for arm in silvcpu prod off silv2048; do grep -q "rc=0" "$S/$arm-64009001.done" || ok=0; done
  for arm in silv2048 silvcpu; do grep -q "ooc-mcts-silver-resolver\] silver_sims=64" "$S/$arm-64009001.log" || ok=0; done
  for arm in prod; do grep -q "ooc-mcts-silver-resolver" "$S/$arm-64009001.log" && ok=0; grep -q "combat_model=selfplay/models/combat_transition_deepsets_lizard_t2.native" "$S/$arm-64009001.log" || ok=0; done
  grep -q "scope=override" "$S/silv2048-64009001.log" || ok=0
  { cat "$S"/*.done; grep -h "^BEST  " "$S"/*.log; } > "$S/summary.txt"
  if [ $ok = 1 ]; then cp "$S/summary.txt" "$SHARE/SMOKE_PASS"; else cp "$S/summary.txt" "$SHARE/SMOKE_FAIL"; fi
  cat "$S/summary.txt" ;;
run)
  [ -f "$OUT/FROZEN.txt" ] || stop "run setup first"
  { for lo in $(blocks); do echo "silv2048 $lo 8"; done
    for lo in $(blocks); do echo "prod $lo 8"; echo "silvcpu $lo 8"; done
    for lo in $(blocks); do echo "off $lo 8"; done; } > "$OUT/units.txt"
  xargs -P 4 -L 1 bash "$D/run_unit.sh" "$REPO" "$RUN" "$OUT" < "$OUT/units.txt"
  n=$(ls "$OUT"/*.done 2>/dev/null | wc -l)
  [ "$n" = 16 ] && { echo "finished=$(date -u +%FT%TZ)"; cat "$OUT"/*.done; grep -h "bestbench-seed-failure" "$OUT"/*.log;
    sha256sum "$OUT"/*.csv; } > "$OUT/DONE.txt"
  echo "units done: $n/16" ;;
status)
  echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/16"; cat "$OUT"/*.done 2>/dev/null; grep -h "bestbench-seed-failure" "$OUT"/*.log 2>/dev/null
  pgrep -fa "one_combat bestbench" | wc -l ;;
*) stop "unknown command $CMD" ;;
esac
