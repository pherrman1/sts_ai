#!/bin/bash
# usage: runT.sh NAME DATA_GLOB_FILE [distill.py args...] -- an uncached Stage-T run (compact rows, 4 loader workers)
set -u
NAME=$1; DATAFILE=$(realpath $2); shift 2
W=~/Documents/sts/az-gen2-sweep; OUT=~/h1distill/gen2/sweep/$NAME
mkdir -p $OUT
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
cd $W
{ echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)"; echo "data $DATAFILE ($(wc -l < $DATAFILE) files)"; echo "args $*"; } > $OUT/train.log
/usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py ~/h1distill/silverbot-84ab3ea $OUT \
  --data $(cat $DATAFILE) --extra-inputs --select fold --device cuda --amp --epochs 20 --patience 3 --pack --val-at-end --value-k 32 \
  --threads 1 --workers 4 --compact "$@" >> $OUT/train.log 2>&1
echo "EXIT $?" >> $OUT/train.log
