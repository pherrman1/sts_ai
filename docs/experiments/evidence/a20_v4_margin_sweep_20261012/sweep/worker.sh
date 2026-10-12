#!/usr/bin/env bash
# §448 margin sweep worker. Usage (from a clean sts_ai checkout, NOT on /mnt/project-files):
#   bash worker.sh setup W   # W=1..8: checkout 4a407a0c, build, check hashes, stage in $HOME/sweep-wWW
#   bash worker.sh run W     # 13 units (one per arm, 16 seeds each), 4 at a time; writes tar + DONE to share
#   bash worker.sh status W
set -uo pipefail
CMD=${1:-} W=${2:-0}
[[ "$W" =~ ^[1-8]$ ]] || { echo "STOP: W must be 1..8"; exit 1; }
WW=$(printf %02d "$W")
SHARE=/mnt/project-files/a20-v4-at-a0-448/sweep
RUN=$HOME/sweep-w$WW OUT=$HOME/sweep-w$WW/out
CODE=4a407a0c942f7c1b328f5cebe273dfd0e6843839
EXPECT_BIN=f085352be42832c9ceada12a816a7d36a32282dc2d38aa14cee974e1cb83f3b2
A20=08d239f9aeaff7cdd57afb2b45a9cbbd1495b1dc9ab51dc09f3c70a61d186b15
A0=e62abd83
LO=$((81000000 + 16*(W-1)))
ARMS="a20_m0 a20_m0.25 a20_m0.5 a20_m1 a20_m2 a20_m4 a0_m0 a0_m0.25 a0_m0.5 a0_m1 a0_m2 a0_m4 heur"
stop() { echo "STOP: $*"; exit 1; }
REPO="$(git rev-parse --show-toplevel)" || stop "run inside the sts_ai checkout"
case "$REPO" in /mnt/project-files*) stop "checkout must not be on /mnt/project-files";; esac
case $CMD in
setup)
  cd "$REPO"; git fetch -q origin main || true
  git checkout -q "$CODE" || stop "cannot check out $CODE"
  git submodule update --init --recursive >/dev/null || stop submodules
  cmake --preset linux-gcc-release >/dev/null && cmake --build --preset linux-gcc-build --target one_combat -j4 >/dev/null || stop "build failed"
  mkdir -p "$OUT"
  cp build/linux-gcc-release/one_combat "$RUN/one_combat"
  [ "$(sha256sum "$RUN/one_combat" | cut -d' ' -f1)" = "$EXPECT_BIN" ] || stop "binary hash mismatch"
  cp /mnt/project-files/v4-a20-retrain/models/v4_a20_r12.native "$RUN/" ; cp selfplay/models/ooc_strategic_tok_final.native "$RUN/"
  [ "$(sha256sum "$RUN/v4_a20_r12.native" | cut -d' ' -f1)" = "$A20" ] || stop "A20 model hash"
  sha256sum "$RUN/ooc_strategic_tok_final.native" | grep -q "^$A0" || stop "A0 model hash"
  echo "$CODE" > "$RUN/GITSHA"; cp "$SHARE/worker.sh" "$RUN/worker.sh"
  echo "setup ok W=$W seeds $LO..$((LO+15))" ;;
unit)  # internal: unit W ARM
  ARM=$3; base=$OUT/$ARM-$LO
  [ -f "$base.done" ] && exit 0
  case $ARM in a20_*) M=$RUN/v4_a20_r12.native;; a0_*|heur) M=$RUN/ooc_strategic_tok_final.native;; *) stop "arm";; esac
  case $ARM in heur) MG=1000000;; *) MG=${ARM#*_m};; esac
  cd "$REPO"
  env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=$HOME STS_EXECUTABLE_GIT_SHA=$CODE \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_OOC_STRATEGIC_TOK_NN=$M \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MAP=1 STS_OOC_STRATEGIC_MARGIN=$MG \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 STS_OOC_MCTS=0 \
    STS_OOC_DECISION_TRACE=$base.trace.jsonl STS_OOC_STRATEGIC_TRACE=$base.v4.csv \
    timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 16 0 $LO $base.csv > $base.log 2>&1
  echo "arm=$ARM lo=$LO rc=$? margin=$MG model=$(basename $M)" > $base.done ;;
run)
  [ -x "$RUN/one_combat" ] || stop "run setup first"
  for a in $ARMS; do echo "$W $a"; done | xargs -P 4 -L 1 bash "$RUN/worker.sh" unit
  n=$(ls "$OUT"/*.done | wc -l); [ "$n" = 13 ] || stop "only $n/13 units done"
  cd "$HOME/sweep-w$WW" && tar czf "w$WW.tar.gz" out && cp "w$WW.tar.gz" "$SHARE/" && sleep 10
  { echo "finished=$(date -u +%FT%TZ) W=$W seeds $LO..$((LO+15))"; cat out/*.done; grep -h "seed-failure" out/*.log
    echo "tar_sha256=$(sha256sum w$WW.tar.gz | cut -d' ' -f1)"; } > "$SHARE/DONE-w$WW.txt"
  cmp "w$WW.tar.gz" "$SHARE/w$WW.tar.gz" && echo "uploaded w$WW.tar.gz OK" ;;
status) echo "done $(ls "$OUT"/*.done 2>/dev/null | wc -l)/13; running $(pgrep -x one_combat | wc -l)"; cat "$OUT"/*.done 2>/dev/null ;;
*) stop "unknown command" ;;
esac
