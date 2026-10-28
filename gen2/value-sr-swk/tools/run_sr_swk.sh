#!/bin/bash
# #903 (issue #883): SR_crn_r2's seeds 1-2 recipe (../../value-sr-crn/tools/run_sr_crn.sh seeds, §649) with ONE change:
# the common-seed TRAIN groups carry swkeyed labels (survival-weighted, event-keyed rollouts, §703) instead of §644's.
# Same groups, rows, records and X2-B (only `target` differs); round-2 TRAIN groups unchanged. Plan:
# docs/experiments/evidence/ooc_swkeyed_labels_20261028/PLAN.md on main's PR #903 branch.
# usage: run_sr_swk.sh [S...]   (default 1 2; one after the other)
set -u
T=$(cd "$(dirname "$0")/../../value-sr-crn/tools" && pwd); R=~/h1distill/gen2/valuesrswk; mkdir -p $R/runs
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $R/run_sr_swk.log; }
W=~/Documents/sts/az-gen2-vdistill; cp $W/tools/heart1/student_inputs.py $W/tools/heart1/capture_provenance.py $T/
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; H1=~/h1distill/gen2/heart1/heart1.pt
ROWS=$(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz)
DC=$(cd "$(dirname "$0")/../data" && pwd)/crn_train_groups_swk.jsonl.gz; DR=$(cd $T/../../value-sr/data && pwd)/r2_train_groups.jsonl.gz
DB=$R/crn_swk_r2_train_groups.jsonl.gz; cat $DC $DR > $DB.$$ && mv $DB.$$ $DB  # gzip members concatenate; sr_load reads both
run() { n=$1; D=$2; shift 2; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  { echo "distill.py sha256 $(sha256sum $T/distill.py | cut -c1-64) monotone.py $(sha256sum $T/monotone.py | cut -c1-64) heart1 $(sha256sum $H1 | cut -c1-64) groups $(sha256sum $D | cut -c1-64)"
    echo "stack $(python3 -c 'import torch, sys; print("python", sys.version.split()[0], "torch", torch.__version__, "cuda", torch.version.cuda, "cudnn", torch.backends.cudnn.version())')"
    echo "args $*"; } > $R/runs/$n/train.log
  /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 $T/distill.py $SB $R/runs/$n \
    --data $ROWS --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
    --pack --val-at-end --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
    --seed 0 --init $SEL --value-weight 0.5 --value-teacher-alpha 1 --cf-teacher $H1 --cf-report --mono-report \
    --mono-weight 0.3 --sr-data $D --sr-workers 3 --sr-weight 1 --save-epochs "$@" >> $R/runs/$n/train.log 2>&1 < /dev/null
  echo "EXIT $?" >> $R/runs/$n/train.log; log "run $n $(tail -1 $R/runs/$n/train.log)"; }
for s in ${@:-1 2}; do run SR_swk_r2_s$s $DB --seed $s --patience 0; done
log "SR SWK SEEDS ${@:-1 2} DONE"
