#!/bin/bash
# usage: run.sh NAME [distill.py args...] -- one run of the gen-2 pick recipe (data branch e07ad88f gen2/sweep/tools/run.sh)
# with the --mono-* distill.py; W = scratch clone whose tools/heart1/distill.py is the sweep's file + apply_mono.py.
set -u
NAME=$1; shift
W=~/Documents/sts/value-mono; OUT=~/h1distill/gen2/mono/$NAME
mkdir -p $OUT
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
cd $W
{ echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)" \
       "monotone.py sha256 $(sha256sum tools/heart1/monotone.py | cut -c1-64)"; echo "args $*"; } > $OUT/train.log
/usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py ~/h1distill/silverbot-84ab3ea $OUT \
  --data ~/Documents/sts/az-gen2-data/gen2/rows/*.capture.jsonl.gz \
  --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 --pack --val-at-end --value-k 32 \
  --threads 1 --workers 4 --cache ~/h1distill/gen2/cache \
  --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 --value-weight 0.3 \
  --init /home/philippherrmann/h1distill/E_sel/E_d64_sel_xin/student.pt "$@" >> $OUT/train.log 2>&1
echo "EXIT $?" >> $OUT/train.log
