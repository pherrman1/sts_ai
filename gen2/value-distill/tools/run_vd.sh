#!/bin/bash
# AZ gen 2 value distillation (phase 2): wait for a free GPU, label teacher values, train, probe.
set -u
cd ~/h1distill/gen2/vdistill
log() { echo "$(date -u +%FT%TZ) $*"; }
busy() { ps -eo args | grep -E "^python3 .*(distill|label_teacher|label_value)\.py" | grep -v "gen2/vdistill" | grep -q .; }
idle=0
while [ $idle -lt 10 ]; do if busy; then idle=0; else idle=$((idle+1)); fi; sleep 30; done
log "GPU free (5 min without other training)"
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1 STS_HEART1_TOOLS=$HOME/Documents/sts/az-gen2-vdistill/tools/heart1
L=~/h1distill/gen2/tools/label_value.py; SB=~/h1distill/silverbot-84ab3ea; ROWS=$(ls ~/Documents/sts/az-gen2-data/gen2/rows/*.gz)
[ -f rows_T1.done ] || { nice python3 $L $SB ~/h1distill/gen2/sweep/T1_heart1_lr1e-4_a1_v1_bs256_s0/student.pt rows_T1 --heads 8 --bs 32 --amp --data $ROWS > label_T1.log 2>&1 && touch rows_T1.done; } || { log "label T1 failed"; exit 1; }
log "labeled T1"
[ -f rows_h1raw.done ] || { nice python3 $L $SB ~/h1distill/gen2/heart1/heart1.pt rows_h1raw --heads 8 --bs 32 --amp --data $ROWS > label_h1raw.log 2>&1 && touch rows_h1raw.done; } || { log "label raw heart1 failed"; exit 1; }
log "labeled raw heart1"
W=~/Documents/sts/az-gen2-vdistill; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt
run() { n=$1; shift; mkdir -p runs/$n; grep -q "^EXIT 0" runs/$n/train.log 2>/dev/null && return
  ( cd $W; { echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)"; echo "args $*"; } > ~/h1distill/gen2/vdistill/runs/$n/train.log
    /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py $SB ~/h1distill/gen2/vdistill/runs/$n \
      --data $(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz) --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
      --pack --val-at-end --value-k 32 --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
      --seed 0 --init $SEL "$@" >> ~/h1distill/gen2/vdistill/runs/$n/train.log 2>&1 < /dev/null
    echo "EXIT $?" >> ~/h1distill/gen2/vdistill/runs/$n/train.log ); log "run $n $(tail -1 runs/$n/train.log)"; }
run VD_T1_alpha1_v0.3 --value-weight 0.3 --value-teacher-alpha 1
run VD_T1_alpha0.5_v0.3 --value-weight 0.3 --value-teacher-alpha 0.5
run VD_T1_alpha1_v1 --value-weight 1 --value-teacher-alpha 1
# baseline: same uncached code path, z only (alpha 0), to separate code-path from target effects
run VD_T1rows_alpha0_v0.3 --value-weight 0.3
for n in VD_T1_alpha1_v0.3 VD_T1_alpha0.5_v0.3 VD_T1_alpha1_v1 VD_T1rows_alpha0_v0.3; do
  [ -f runs/$n/mono.txt ] || OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice python3 ~/h1distill/gen2/vdistill/mono.py runs/$n/student.pt > runs/$n/mono.txt 2>&1
done
log "VD DONE"
