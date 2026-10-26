#!/bin/bash
# Value-head research: sibling-ranking loss and auxiliary heads on the M0.3 recipe (gen2/value-cf run_cf.sh, M0.3 line).
# usage: run_sr.sh smoke | all | seeds     (tools dir = this script's dir: distill.py, monotone.py, sr_groups.py; student_inputs.py
# and capture_provenance.py are copied in from the vdistill worktree; groups in ../data/r2_train_groups.jsonl.gz)
set -u
T=$(cd "$(dirname "$0")" && pwd); R=~/h1distill/gen2/valuesr; mkdir -p $R/runs
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $R/run_sr.log; }
W=~/Documents/sts/az-gen2-vdistill; cp $W/tools/heart1/student_inputs.py $W/tools/heart1/capture_provenance.py $T/
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; H1=~/h1distill/gen2/heart1/heart1.pt
ROWS=$(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz); D=$(cd $T/../data && pwd)/r2_train_groups.jsonl.gz
run() { n=$1; shift; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  { echo "distill.py sha256 $(sha256sum $T/distill.py | cut -c1-64) monotone.py $(sha256sum $T/monotone.py | cut -c1-64) heart1 $(sha256sum $H1 | cut -c1-64) groups $(sha256sum $D | cut -c1-64)"; echo "args $*"; } > $R/runs/$n/train.log
  /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 $T/distill.py $SB $R/runs/$n \
    --data $ROWS --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
    --pack --val-at-end --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
    --seed 0 --init $SEL --value-weight 0.5 --value-teacher-alpha 1 --cf-teacher $H1 --cf-report --mono-report \
    --mono-weight 0.3 --sr-data $D --sr-workers 3 "$@" >> $R/runs/$n/train.log 2>&1 < /dev/null
  echo "EXIT $?" >> $R/runs/$n/train.log; log "run $n $(tail -1 $R/runs/$n/train.log)"; }
if [ "${1:-}" = seeds ]; then  # PLAN.md gate: a PASS arm gets seeds 1-2 before any online test (SR_w1 passed, 2026-10-22)
  run SR_w1_s1 --sr-weight 1 --seed 1
  run SR_w1_s2 --sr-weight 1 --seed 2
  log "SR SEEDS DONE"; exit; fi
if [ "${1:-}" = smoke ]; then  # 1 epoch on few files: both new code paths + timing only
  ROWS=$(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz | head -48); run smoke_sr1 --sr-weight 1 --aux-weight 0.3 --stop-after 1; exit; fi
run SR_w0.3 --sr-weight 0.3     # sibling-ranking loss (all arms: M0.3 recipe, --sr-data reports holdout concordance)
run AUX0.3 --aux-weight 0.3     # training-only heads: passed next boss, reached act 4, final floor / 55
run SR_w1 --sr-weight 1
run SR_w0.1 --sr-weight 0.1
log "SR DONE"
