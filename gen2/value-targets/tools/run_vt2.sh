#!/bin/bash
# seeds 1 and 2 of VT_nstep5_cal_l1 (AZ thread 19:40Z), after the vdistill queue (VD4 DONE)
set -u
cd ~/h1distill/gen2/vtargets
log() { echo "$(date -u +%FT%TZ) $*"; }
until grep -q "VD4 DONE" ~/h1distill/gen2/vdistill/run_vd.log 2>/dev/null; do sleep 30; done; log "start seeds"
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea; W=~/Documents/sts/az-gen2-vdistill; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; R=~/h1distill/gen2/vtargets
run() { n=$1; k=$2; shift 2; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  ( cd $W; { echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)"; echo "args $k $*"; } > $R/runs/$n/train.log
    /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py $SB $R/runs/$n \
      --data $(ls $R/rows/*.gz) --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
      --pack --val-at-end $k --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
      --value-weight 0.3 --init $SEL "$@" >> $R/runs/$n/train.log 2>&1 < /dev/null
    echo "EXIT $?" >> $R/runs/$n/train.log ); log "run $n $(tail -1 $R/runs/$n/train.log)"; }
K="--value-k 32"
run VT_nstep5_cal_l1_s1 "$K" --value-target-field nstep_v_cal --value-teacher-alpha 1 --seed 1
run VT_nstep5_cal_l1_s2 "$K" --value-target-field nstep_v_cal --value-teacher-alpha 1 --seed 2
log "VT2 DONE"
