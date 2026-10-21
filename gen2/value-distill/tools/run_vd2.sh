#!/bin/bash
# Follow-up (Philipp 16:25Z): value distillation without the K=32 value subsample. The K=32 alpha-0 control is dropped
# (Stage S's pick is that control; the uncached path was checked identical to the cached one).
set -u
cd ~/h1distill/gen2/vdistill
log() { echo "$(date -u +%FT%TZ) $*"; }
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea
until grep -q "^EXIT" runs/VD_T1_alpha1_v1/train.log 2>/dev/null; do sleep 30; done; log "run VD_T1_alpha1_v1 $(tail -1 runs/VD_T1_alpha1_v1/train.log)"
W=~/Documents/sts/az-gen2-vdistill; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt
run() { n=$1; shift; mkdir -p runs/$n; grep -q "^EXIT 0" runs/$n/train.log 2>/dev/null && return
  ( cd $W; { echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)"; echo "args $*"; } > ~/h1distill/gen2/vdistill/runs/$n/train.log
    /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py $SB ~/h1distill/gen2/vdistill/runs/$n \
      --data $(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz) --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
      --pack --val-at-end --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
      --seed 0 --init $SEL "$@" >> ~/h1distill/gen2/vdistill/runs/$n/train.log 2>&1 < /dev/null
    echo "EXIT $?" >> ~/h1distill/gen2/vdistill/runs/$n/train.log ); log "run $n $(tail -1 runs/$n/train.log)"; }
run VDF_T1_alpha1_v0.3 --value-weight 0.3 --value-teacher-alpha 1
run VDF_T1_alpha1_v1 --value-weight 1 --value-teacher-alpha 1
for n in VDF_T1_alpha1_v0.3 VDF_T1_alpha1_v1 VD_T1_alpha1_v0.3 VD_T1_alpha0.5_v0.3 VD_T1_alpha1_v1; do
  [ -f runs/$n/mono.txt ] || [ ! -f runs/$n/student.pt ] || OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice python3 ~/h1distill/gen2/vdistill/mono.py runs/$n/student.pt > runs/$n/mono.txt 2>&1
  log "probed $n"
done
log "VD2 DONE"
