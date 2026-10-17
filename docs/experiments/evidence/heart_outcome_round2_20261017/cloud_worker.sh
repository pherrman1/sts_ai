#!/usr/bin/env bash
# Heart-outcome round 2 cloud worker wrapper. Run from the repository checkout; it fetches RUN_COMMIT itself.
# setup is local-only: clone + build under $HOME, no share writes. run copies the weights from the read-only
# share copy, re-prepares and hash-checks the frozen plan/bundle, runs `heart_outcome_round2.py worker`
# unchanged, and writes only deliveries/wWW (or rWW-H for a lost-worker half rerun).
# Usage: bash cloud_worker.sh setup W | run W ACTIVATION_SHA256 [H] | status W   (W unpadded; H = rerun half 0/1)
set -euo pipefail
SOURCE=d8fd2a105a8d2a481b7639e26c683f75e382e3d4
STUDENT_C=eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509
BINARY_SHA=0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52
PLAN_SHA=c88256cea6734fe0a0e891c88bf9c40f67fb5d78ce5e45d0ff7ac9f707c06cfc
BUNDLE_SHA=5810761da0ac09d5ba8a476655e5cd225906a0a86a72f100a65d090c3d40b59c
WORKERS=45
PER_WORKER="34 10 20"
SIBLING_EVERY=8   # 0 = no sibling subsample (then PLAN_SHA babf5c7a…, same bundle)
SH=/mnt/project-files/heart-outcome-round2
R=/home/user/sts_ai
S=$HOME/heart2-src
W="${2:-}"
[[ "$W" =~ ^(0|[1-9][0-9]?)$ ]] && [ "$W" -lt "$WORKERS" ] || { echo "STOP: W must be 0..$((WORKERS-1)) unpadded"; exit 2; }
WW=$(printf %02d "$W")
L=$HOME/heart2-w$WW
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
  echo "setup ok: W=$W source $SOURCE producer $got cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs) nproc=$(nproc) boot=$(cat /proc/sys/kernel/random/boot_id)"
  ;;
run)
  ACT="${3:-}"
  H="${4:-}"
  if [ -n "$H" ]; then
    [[ "$H" =~ ^[01]$ ]] || { echo "STOP: half must be 0 or 1"; exit 2; }
    D=$SH/deliveries/r$WW-$H
  fi
  [[ "$ACT" =~ ^[0-9a-f]{64}$ ]] || { echo "STOP: give the approved activation SHA256"; exit 2; }
  [ -x $S/build/linux-gcc-release/one_combat ] && [ ! -e $L/campaign ] || { echo "STOP: no setup or worker already started here"; exit 1; }
  [ ! -e $D ] || { echo "STOP: delivery dir $D already exists on the share"; exit 1; }
  cp /mnt/project-files/student-c-488/studentc.bin $L/studentc.bin
  [ "$(sha256sum $L/studentc.bin | cut -d' ' -f1)" = "$STUDENT_C" ] || { echo "STOP: studentc sha"; exit 1; }
  python3 $S/tools/heart_outcome_round2.py prepare --repo $S --binary $S/build/linux-gcc-release/one_combat \
    --student $L/studentc.bin --out $L/campaign --workers $WORKERS --per-worker $PER_WORKER --sibling-every $SIBLING_EVERY > $L/prepare.log 2>&1 \
    || { echo "STOP: prepare failed"; tail -5 $L/prepare.log; exit 1; }
  [ "$(sha256sum $L/campaign/plan.json | cut -d' ' -f1)" = "$PLAN_SHA" ] || { echo "STOP: plan sha differs"; exit 1; }
  [ "$(sha256sum $L/campaign/bundle/bundle.json | cut -d' ' -f1)" = "$BUNDLE_SHA" ] || { echo "STOP: bundle sha differs"; exit 1; }
  cp $SH/campaign/activation.json $SH/campaign/COHORT-STARTED.json $L/campaign/
  cp -r $SH/campaign/cloud-canary $L/campaign/cloud-canary
  [ "$(sha256sum $L/campaign/activation.json | cut -d' ' -f1)" = "$ACT" ] || { echo "STOP: activation sha differs"; exit 1; }
  mkdir -p $D
  B=$L/campaign/bundle
  N=$(python3 -c "import json,sys;p=json.load(open('$L/campaign/plan.json'));n=sum(s['worker']==$W for s in p['sources']);print((n+1-int('${H:-0}'))//2 if '$H' else n)")
  ( while [ ! -f $L/out/worker-receipt.json ]; do
      n=$(find $L/out -name '*.receipt.json' 2>/dev/null | wc -l || true)
      echo "$(date -u +%FT%TZ) receipts=$n/$N one_combat=$(pgrep -c one_combat || true)" > $D/progress.txt.partial && mv $D/progress.txt.partial $D/progress.txt
      sleep 300; done ) &
  set +e
  python3 $B/heart_outcome_round2.py worker --plan $L/campaign/plan.json --bundle $B \
    --activation $L/campaign/activation.json --out $L/out --worker $W --activation-sha256 $ACT ${H:+--half $H} > $L/worker.log 2>&1
  rc=$?
  set -e
  put $L/worker.log $D/worker.log || true
  [ -f $L/out/worker-started.json ] && put $L/out/worker-started.json $D/worker-started.json
  if [ -f $L/out/worker-receipt.json ]; then
    for f in train.tar.gz validation.tar.gz SEALED-confirm.tar.gz; do put $L/out/$f $D/$f || { echo "STOP: export $f" >> $L/worker.log; exit 1; }; done
    put $L/out/worker-receipt.json $D/worker-receipt.json   # receipt last: its presence means the archives are there
    echo "WORKER_OK W=$W${H:+ H=$H} rc=$rc receipt=$(sha256sum < $D/worker-receipt.json | cut -d' ' -f1)" >> $L/worker.log
  else
    # Partial raw outputs may include CONFIRM sources, hence the sealed name; never unpacked by the lead.
    [ -d $L/out ] && tar -czf $L/SEALED-partial-out.tar.gz -C $L out && put $L/SEALED-partial-out.tar.gz $D/SEALED-partial-out.tar.gz || true
    echo "STOP: worker exited rc=$rc without worker-receipt.json" >> $L/worker.log
  fi
  ;;
status)
  echo "receipts=$(find $L/out -name '*.receipt.json' 2>/dev/null | wc -l) one_combat=$(pgrep -c one_combat || true)"
  tail -2 $L/worker.log 2>/dev/null || true
  ;;
*) echo "usage: setup W | run W ACTIVATION_SHA256 [H] | status W"; exit 2;;
esac
