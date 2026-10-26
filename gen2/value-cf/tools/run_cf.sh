#!/bin/bash
# Value-head research: counterfactual teacher-delta distillation (raw heart1 deltas) on the VDF_T1 v0.5 recipe.
# usage: run_cf.sh smoke | all     (tools dir = this script's dir: distill.py, monotone.py; student_inputs.py and
# capture_provenance.py are copied in from the vdistill worktree)
set -u
T=$(cd "$(dirname "$0")" && pwd); R=~/h1distill/gen2/valuecf; mkdir -p $R/runs
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $R/run_cf.log; }
W=~/Documents/sts/az-gen2-vdistill; cp $W/tools/heart1/student_inputs.py $W/tools/heart1/capture_provenance.py $T/
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; H1=~/h1distill/gen2/heart1/heart1.pt
ROWS=$(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz)
run() { n=$1; shift; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  { echo "distill.py sha256 $(sha256sum $T/distill.py | cut -c1-64) monotone.py $(sha256sum $T/monotone.py | cut -c1-64) heart1 $(sha256sum $H1 | cut -c1-64)"; echo "args $*"; } > $R/runs/$n/train.log
  /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 $T/distill.py $SB $R/runs/$n \
    --data $ROWS --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
    --pack --val-at-end --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
    --seed 0 --init $SEL --value-weight 0.5 --value-teacher-alpha 1 --cf-teacher $H1 --cf-report --mono-report "$@" \
    >> $R/runs/$n/train.log 2>&1 < /dev/null
  echo "EXIT $?" >> $R/runs/$n/train.log; log "run $n $(tail -1 $R/runs/$n/train.log)"; }
if [ "${1:-}" = smoke ]; then  # 1 epoch on few files: code path + timing only
  ROWS=$(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz | head -48); run smoke_cf1 --cf-weight 1 --stop-after 1; exit; fi
run CF_base                       # control: must reproduce VDF_T1_alpha1_v0.5 (sel BCE ~0.542); baseline deltas
run CF_w0.3 --cf-weight 0.3
run CF_w1 --cf-weight 1
run CF_w3 --cf-weight 3
run M0.3 --mono-weight 0.3        # monotonicity hinge (#777) on the same recipe, for comparison
log "CF DONE"
