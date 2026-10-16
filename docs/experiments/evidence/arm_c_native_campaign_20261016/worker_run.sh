#!/usr/bin/env bash
# Arm C fresh cohort worker; run from the repository checkout at the pinned run commit.
# Usage: bash worker_run.sh setup W | run W | status W   (W unpadded, 1..32)
set -euo pipefail
PRODUCER=86a7569fe56cfdd2f635018147f005b16870598c53c7c164a5d1edd994ecbacf
PLAN_SHA=b4c28ae0ebeb07aa5a0002b3c4d18c406305eb578285259cf49ac91d38a5f89e
F=/mnt/project-files/arm-c-native-campaign
C=$F/collect
LEAD_CPU="Intel(R) Xeon(R) Processor @ 2.10GHz"
R=/home/user/sts_ai
W="${2:-}"
[[ "$W" =~ ^([1-9]|[12][0-9]|3[0-2])$ ]] || { echo "STOP: W must be 1..32 unpadded"; exit 2; }
WW=$(printf %02d "$W")
L=$HOME/armc-w$WW
case "${1:-}" in
setup)
  [ -f $C/deadline.json ] || { echo "STOP: no deadline.json; collection not started"; exit 1; }
  cd $R
  # The brief checks out the pinned run commit and runs this script from that checkout.
  git submodule update -q --init --recursive
  [ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "STOP: dirty checkout"; exit 1; }
  cmake --preset linux-gcc-release > $HOME/armc-configure.log 2>&1
  cmake --build --preset linux-gcc-build --target one_combat --parallel 4 > $HOME/armc-build.log 2>&1 || { echo "STOP: build failed"; tail -20 $HOME/armc-build.log; exit 1; }
  got=$(sha256sum build/linux-gcc-release/one_combat | cut -d' ' -f1)
  [ "$got" = "$PRODUCER" ] || { echo "STOP: producer sha $got"; exit 1; }
  mkdir -p $L
  [ -d $L/bundle ] || python3 tools/heart_distill_native_worker.py bundle . build/linux-gcc-release/one_combat /mnt/project-files/student-c-488/studentc.bin $L/bundle
  cp $F/plan32.json $L/plan32.json
  [ "$(sha256sum $L/plan32.json | cut -d' ' -f1)" = "$PLAN_SHA" ] || { echo "STOP: plan sha"; exit 1; }
  echo "setup ok: W=$W commit $(git rev-parse HEAD) producer $got cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs) nproc=$(nproc)"
  ;;
run)
  cd $R
  # Cross-CPU qualification: on a CPU model other than the lead canary's, also repeat frozen canary
  # 110163995 (capture ON) next to the two sources; the lead compares its bytes before any pooling.
  cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)
  CAN=""
  if [ "$cpu" != "$LEAD_CPU" ] && [ ! -f $C/canaries/w$WW-canary.tar.gz ]; then
    CAN=$L/canary-$(date +%s)
    python3 tools/heart_distill_native_worker.py unit $L/plan32.json $L/bundle $CAN 110163995 canary-second-w$WW > $L/canary.log 2>&1 &
    CPID=$!
  fi
  if python3 tools/heart_distill_native_worker.py worker $L/plan32.json $PLAN_SHA $L/bundle $L/out $C $W > $L/worker.log 2>&1; then
    ok="WORKER_OK $(tail -1 $L/worker.log)"
  else
    ok="STOP: worker exited rc=$?"
  fi
  if [ -n "$CAN" ]; then  # canary problems are reported, never fatal to the source export above
    set +e
    wait $CPID
    mkdir -p $C/canaries $CAN
    echo "cpu=$cpu" > $CAN/CPU.txt; cp $L/canary.log $CAN/
    tar -czf $L/w$WW-canary.tar.gz -C $L $(basename $CAN) \
      && cp $L/w$WW-canary.tar.gz $C/canaries/w$WW-canary.tar.gz.partial \
      && mv $C/canaries/w$WW-canary.tar.gz.partial $C/canaries/w$WW-canary.tar.gz \
      && [ "$(sha256sum < $L/w$WW-canary.tar.gz)" = "$(sha256sum < $C/canaries/w$WW-canary.tar.gz)" ] \
      || ok="$ok CANARY_EXPORT_FAILED"
    set -e
  fi
  echo "$ok" >> $L/worker.log
  ;;
status)
  ls $C/receipts 2>/dev/null | grep -c . || true; pgrep -c one_combat || true; tail -2 $L/worker.log 2>/dev/null || true
  ;;
*) echo "usage: setup|run|status W"; exit 2;;
esac
