#!/usr/bin/env bash
# Observed Heart-outcome cohort (§497) cloud worker wrapper. Run from the repository checkout at RUN_COMMIT.
# The frozen producer source 7527b5d is cloned separately; this wrapper only rebuilds/verifies the frozen
# bundle locally, runs `heart_outcome_collect.py worker` unchanged, and exports its outputs to the share.
# setup is local-only: it clones and builds under $HOME and touches no share path. run copies the weights from the
# read-only share copy, re-prepares and hash-checks the frozen plan/bundle, runs the worker, and writes only deliveries/wWW.
# Usage: bash cloud_worker.sh setup W | run W ACTIVATION_SHA256 | status W   (W unpadded, 0..44)
set -euo pipefail
SOURCE=7527b5d5d07467688101212660461995665512b9
TRANSPORT=d65a365599bb0e32a5b26a4c59aa19dcd1ca0195
STUDENT_C=eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509
BINARY_SHA=178e7076934097987e473ab04c2dc80eec5368f9dcb12b274a631bad62f43e4e
PLAN_SHA=4b49a40427dde2470044847e8e843cc349a460e183d6fa2ddbdda4c0494d14a3
BUNDLE_SHA=836a34129c99bfd68e691ed802f0a403cd75e37db7effd0e1b01f51b4697f6d5
SH=/mnt/project-files/heart-outcome-collection
R=/home/user/sts_ai
S=$HOME/heart-src
W="${2:-}"
[[ "$W" =~ ^([0-9]|[1-3][0-9]|4[0-4])$ ]] || { echo "STOP: W must be 0..44 unpadded"; exit 2; }
WW=$(printf %02d "$W")
L=$HOME/heart-w$WW
D=$SH/deliveries/w$WW
put() {  # copy one file to the share atomically and verify the share bytes
  cp "$1" "$2.partial" && mv "$2.partial" "$2"
  [ "$(sha256sum < "$1")" = "$(sha256sum < "$2")" ] || { echo "STOP: share copy mismatch $2"; return 1; }
}
case "${1:-}" in
setup)
  [ ! -e $L ] || { echo "STOP: $L already exists (container reused); report, do not rerun"; exit 1; }
  mkdir -p $L
  [ -d $S ] || git clone -q --no-checkout $R $S
  git -C $S checkout -q --detach $SOURCE
  git -C $S submodule update -q --init --recursive
  [ "$(git -C $S rev-parse HEAD)" = "$SOURCE" ] || { echo "STOP: source sha"; exit 1; }
  (cd $S && cmake --preset linux-gcc-release > $L/configure.log 2>&1 \
     && cmake --build --preset linux-gcc-build --target one_combat --parallel 4 > $L/build.log 2>&1) \
     || { echo "STOP: build failed"; tail -20 $L/build.log; exit 1; }
  got=$(sha256sum $S/build/linux-gcc-release/one_combat | cut -d' ' -f1)
  [ "$got" = "$BINARY_SHA" ] || { echo "STOP: producer sha $got"; exit 1; }
  echo "setup ok: W=$W source $SOURCE producer $got cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs) nproc=$(nproc) host=$(hostname)"
  ;;
run)
  ACT="${3:-}"
  [[ "$ACT" =~ ^[0-9a-f]{64}$ ]] || { echo "STOP: give the approved activation SHA256"; exit 2; }
  [ -x $S/build/linux-gcc-release/one_combat ] && [ ! -e $L/campaign ] || { echo "STOP: no setup or worker already started here"; exit 1; }
  [ ! -e $D ] || { echo "STOP: delivery dir for w$WW already exists on the share"; exit 1; }
  cp /mnt/project-files/student-c-488/studentc.bin $L/studentc.bin  # read-only share copy, same bytes as $TRANSPORT:bundle/studentc.bin
  [ "$(sha256sum $L/studentc.bin | cut -d' ' -f1)" = "$STUDENT_C" ] || { echo "STOP: studentc sha"; exit 1; }
  python3 $S/tools/heart_outcome_collect.py prepare --repo $S --binary $S/build/linux-gcc-release/one_combat \
    --student $L/studentc.bin --out $L/campaign > $L/prepare.log 2>&1 || { echo "STOP: prepare failed"; tail -5 $L/prepare.log; exit 1; }
  [ "$(sha256sum $L/campaign/plan.json | cut -d' ' -f1)" = "$PLAN_SHA" ] || { echo "STOP: plan sha differs"; exit 1; }
  [ "$(sha256sum $L/campaign/bundle/bundle.json | cut -d' ' -f1)" = "$BUNDLE_SHA" ] || { echo "STOP: bundle sha differs"; exit 1; }
  cp $SH/campaign/activation.json $SH/campaign/COHORT-STARTED.json $L/campaign/
  cp -r $SH/campaign/cloud-canary $L/campaign/cloud-canary
  [ "$(sha256sum $L/campaign/activation.json | cut -d' ' -f1)" = "$ACT" ] || { echo "STOP: activation sha differs"; exit 1; }
  mkdir -p $D
  B=$L/campaign/bundle
  ( while [ ! -f $L/out/worker-receipt.json ]; do
      n=$(find $L/out -name '*.receipt.json' 2>/dev/null | wc -l || true)
      echo "$(date -u +%FT%TZ) receipts=$n/40 one_combat=$(pgrep -c one_combat || true)" > $D/progress.txt.partial && mv $D/progress.txt.partial $D/progress.txt
      sleep 300; done ) &
  set +e
  python3 $B/heart_outcome_collect.py worker --plan $L/campaign/plan.json --bundle $B \
    --activation $L/campaign/activation.json --out $L/out --worker $W --activation-sha256 $ACT > $L/worker.log 2>&1
  rc=$?
  set -e
  put $L/worker.log $D/worker.log || true
  [ -f $L/out/worker-started.json ] && put $L/out/worker-started.json $D/worker-started.json
  if [ -f $L/out/worker-receipt.json ]; then
    for f in train.tar.gz validation.tar.gz SEALED-test.tar.gz; do put $L/out/$f $D/$f || { echo "STOP: export $f" >> $L/worker.log; exit 1; }; done
    put $L/out/worker-receipt.json $D/worker-receipt.json   # receipt last: its presence means the archives are there
    echo "WORKER_OK W=$W rc=$rc receipt=$(sha256sum < $D/worker-receipt.json | cut -d' ' -f1)" >> $L/worker.log
  else
    # Preserve partial raw outputs (may include TEST sources, hence sealed name; never unpacked by the lead).
    [ -d $L/out ] && tar -czf $L/SEALED-partial-out.tar.gz -C $L out && put $L/SEALED-partial-out.tar.gz $D/SEALED-partial-out.tar.gz || true
    echo "STOP: worker exited rc=$rc without worker-receipt.json" >> $L/worker.log
  fi
  ;;
status)
  echo "receipts=$(find $L/out -name '*.receipt.json' 2>/dev/null | wc -l)/40 one_combat=$(pgrep -c one_combat || true)"
  tail -2 $L/worker.log 2>/dev/null || true
  ;;
*) echo "usage: setup W | run W ACTIVATION_SHA256 | status W"; exit 2;;
esac
