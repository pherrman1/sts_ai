#!/bin/bash
# AZ gen 2 value targets (Philipp 17:03Z): search-value targets (calibrated root q, n-step) and training-only aux heads.
# Pick recipe from student_sel, seed 0; uncached --compact; K=32 unless noted. Starts after the no-K teacher queue.
set -u
cd ~/h1distill/gen2/vtargets
log() { echo "$(date -u +%FT%TZ) $*"; }
until grep -q "VD2 DONE" ~/h1distill/gen2/vdistill/run_vd.log; do sleep 30; done; log "start"
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea; W=~/Documents/sts/az-gen2-vdistill; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; R=~/h1distill/gen2/vtargets
run() { n=$1; k=$2; shift 2; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  ( cd $W; { echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)"; echo "args $k $*"; } > $R/runs/$n/train.log
    /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py $SB $R/runs/$n \
      --data $(ls $R/rows/*.gz) --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
      --pack --val-at-end $k --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
      --value-weight 0.3 --seed 0 --init $SEL "$@" >> $R/runs/$n/train.log 2>&1 < /dev/null
    echo "EXIT $?" >> $R/runs/$n/train.log ); log "run $n $(tail -1 $R/runs/$n/train.log)"; }
K="--value-k 32"
run VT_root_cal_l0.5 "$K" --value-target-field root_v_cal --value-teacher-alpha 0.5
run VT_root_cal_l1 "$K" --value-target-field root_v_cal --value-teacher-alpha 1
run VT_nstep5_cal_l1 "$K" --value-target-field nstep_v_cal --value-teacher-alpha 1
run VT_nstep5_cal_l1_noK "" --value-target-field nstep_v_cal --value-teacher-alpha 1
run VT_aux0.3 "$K" --aux-weight 0.3
for n in VT_root_cal_l0.5 VT_root_cal_l1 VT_nstep5_cal_l1 VT_nstep5_cal_l1_noK VT_aux0.3; do
  [ -f runs/$n/mono.txt ] || [ ! -f runs/$n/student.pt ] || OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice python3 ~/h1distill/gen2/vdistill/mono.py runs/$n/student.pt > runs/$n/mono.txt 2>&1
  log "probed $n"
done
log "VT DONE"
