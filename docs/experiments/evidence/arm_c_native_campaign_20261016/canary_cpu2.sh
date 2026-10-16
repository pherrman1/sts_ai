#!/usr/bin/env bash
# Cross-CPU canary: repeat qualification seed 110163995 (capture ON) with the frozen producer.
# Run from the repository checkout at the pinned run commit.
# Usage: bash canary_cpu2.sh setup | bash canary_cpu2.sh run | bash canary_cpu2.sh status
set -euo pipefail
PRODUCER=86a7569fe56cfdd2f635018147f005b16870598c53c7c164a5d1edd994ecbacf
PLAN_SHA=b4c28ae0ebeb07aa5a0002b3c4d18c406305eb578285259cf49ac91d38a5f89e
F=/mnt/project-files/arm-c-native-campaign
R=/home/user/sts_ai
L=$HOME/cpu2
case "${1:-}" in
setup)
  cd $R
  # The brief checks out the pinned run commit and runs this script from that checkout.
  git submodule update -q --init --recursive
  [ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "STOP: dirty checkout"; exit 1; }
  cmake --preset linux-gcc-release > $HOME/cpu2-configure.log 2>&1
  cmake --build --preset linux-gcc-build --target one_combat --parallel 4 > $HOME/cpu2-build.log 2>&1 || { echo "STOP: build failed"; tail -20 $HOME/cpu2-build.log; exit 1; }
  got=$(sha256sum build/linux-gcc-release/one_combat | cut -d' ' -f1)
  [ "$got" = "$PRODUCER" ] || { echo "STOP: producer sha $got"; exit 1; }
  rm -rf $L; mkdir -p $L
  cp $F/plan32.json $L/plan32.json
  [ "$(sha256sum $L/plan32.json | cut -d' ' -f1)" = "$PLAN_SHA" ] || { echo "STOP: plan sha"; exit 1; }
  python3 tools/heart_distill_native_worker.py bundle . build/linux-gcc-release/one_combat /mnt/project-files/student-c-488/studentc.bin $L/bundle
  echo "setup ok: commit $(git rev-parse HEAD) producer $got cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs) nproc=$(nproc)"
  ;;
run)
  cd $R
  python3 tools/heart_distill_native_worker.py unit $L/plan32.json $L/bundle $L/out 110163995 canary-second-cpu2 > $L/unit.log 2>&1 || true
  ( cd $L/out && sha256sum * > ../SHA256SUMS ) || true
  mkdir -p $F/canary-cpu2
  for f in $L/out/* $L/SHA256SUMS $L/unit.log; do cp "$f" $F/canary-cpu2/; done
  for f in $L/out/*; do b=$(basename $f); [ "$(sha256sum $f | cut -d' ' -f1)" = "$(sha256sum $F/canary-cpu2/$b | cut -d' ' -f1)" ] || { echo "STOP: share read-back mismatch $b" | tee -a $L/unit.log; exit 1; }; done
  { echo "finished=$(date -u +%FT%TZ)"; echo "cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"; tail -1 $L/unit.log; cat $L/SHA256SUMS; } > $L/DONE.txt
  cp $L/DONE.txt $F/canary-cpu2/DONE.txt
  ;;
status)
  ls -la $L/out 2>/dev/null | tail -n +2; pgrep -c one_combat || true
  ;;
*) echo "usage: setup|run|status"; exit 2;;
esac
