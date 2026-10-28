#!/bin/bash
# SR head data learning curve (../PLAN.md): SR_crn_r2_s1/s2's command (../../value-sr-crn/tools/run_sr_crn.sh seeds) on
# nested 25 % / 50 % source subsets of its training rows and ranking groups, with the same number of optimizer steps
# (--epochs 20 * 4 / K, one-cycle schedule over the whole run). 100 % = the existing SR_crn_r2_s1 / _s2 runs.
# usage: run_lc.sh smoke | main | split
#   main:  LC25_s1 LC25_s2 LC50_s1 LC50_s2   (primary)
#   split: LC25rows_s1 (rows 25 %, all groups), LC25groups_s1 (all rows, groups 25 %)   (secondary, after main)
# PAR=2 runs two runs side by side (the result does not depend on it).
set -u
T=$(cd "$(dirname "$0")" && pwd); S=$T/../../value-sr-crn/tools; R=~/h1distill/gen2/valuesrlc; mkdir -p $R/runs $R/sub
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $R/run_lc.log; }
W=~/Documents/sts/az-gen2-vdistill; cp $W/tools/heart1/student_inputs.py $W/tools/heart1/capture_provenance.py $S/
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
SB=~/h1distill/silverbot-84ab3ea; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; H1=~/h1distill/gen2/heart1/heart1.pt
ALLROWS=$(ls ~/h1distill/gen2/vdistill/rows_T1/*.gz)
DC=$(cd $S/../data && pwd)/crn_train_groups.jsonl.gz; DR=$(cd $S/../../value-sr/data && pwd)/r2_train_groups.jsonl.gz
DB=$R/crn_r2_train_groups.jsonl.gz; cat $DC $DR > $DB.$$ && mv $DB.$$ $DB
[ "$(sha256sum $DB | cut -c1-8)" = 3f78ae0c ] || { log "groups sha mismatch"; exit 1; }
for k in 1 2 4; do [ -s $R/sub/K$k/subset.json ] || python3 $T/lc_subset.py $k $R/sub/K$k $DB $ALLROWS > /dev/null; done
run() { n=$1; ROWS=$2; D=$3; EP=$4; seed=$5; shift 5; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  { echo "distill.py sha256 $(sha256sum $S/distill.py | cut -c1-64) monotone.py $(sha256sum $S/monotone.py | cut -c1-64) heart1 $(sha256sum $H1 | cut -c1-64) groups $(sha256sum $D | cut -c1-64) rows.txt $(sha256sum $ROWS | cut -c1-64) STS_ACTIVE_POWER_FEATURES=${STS_ACTIVE_POWER_FEATURES-unset}"; echo "args epochs $EP seed $seed $*"; } > $R/runs/$n/train.log
  /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 $S/distill.py $SB $R/runs/$n \
    --data $(cat $ROWS) --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs $EP --patience 0 \
    --pack --val-at-end --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 --lr 1e-4 --anchor-weight 0.3 \
    --seed $seed --init $SEL --value-weight 0.5 --value-teacher-alpha 1 --cf-teacher $H1 --cf-report --mono-report \
    --mono-weight 0.3 --sr-data $D --sr-workers 3 --sr-weight 1 --save-epochs "$@" >> $R/runs/$n/train.log 2>&1 < /dev/null
  echo "EXIT $?" >> $R/runs/$n/train.log; log "run $n $(tail -1 $R/runs/$n/train.log)"; }
k() { echo $R/sub/K$1; }
if [ "${1:-}" = smoke ]; then  # 1 epoch on the 25 % subset: loads, counts, timing
  run smoke_lc $(k 1)/rows.txt $(k 1)/groups.jsonl.gz 80 1 --stop-after 1; exit; fi
P=${PAR:-1}
batch() { local i=0; for spec in "$@"; do run $spec & i=$((i+1)); [ $((i % P)) = 0 ] && wait; done; wait; }
if [ "${1:-}" = main ]; then
  batch "LC25_s1 $(k 1)/rows.txt $(k 1)/groups.jsonl.gz 80 1" "LC25_s2 $(k 1)/rows.txt $(k 1)/groups.jsonl.gz 80 2" \
        "LC50_s1 $(k 2)/rows.txt $(k 2)/groups.jsonl.gz 40 1" "LC50_s2 $(k 2)/rows.txt $(k 2)/groups.jsonl.gz 40 2"
  log "LC MAIN DONE"; exit; fi
if [ "${1:-}" = split ]; then  # one axis at a time; steps matched to the 100 % runs by the row count's epochs
  batch "LC25rows_s1 $(k 1)/rows.txt $(k 4)/groups.jsonl.gz 80 1" "LC25groups_s1 $(k 4)/rows.txt $(k 1)/groups.jsonl.gz 20 1"
  log "LC SPLIT DONE"; exit; fi
echo "usage: run_lc.sh smoke | main | split"; exit 1
