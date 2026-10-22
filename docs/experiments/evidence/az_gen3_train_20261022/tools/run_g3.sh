#!/bin/bash
# AZ gen 3 prior training (PLAN: docs/experiments/evidence/az_gen3_train_20261022/PLAN.md, Philipp 14:16Z 10-22).
# usage: run_g3.sh  (idempotent: finished runs are skipped). Needs: ~/h1distill/gen3 from the data branch (gen3/),
# old rows ~/h1distill/gen2/vtargets/rows (2,688 files), worktree $W with tools/heart1/distill.py sha256 8aac69b6.
set -u
R=~/h1distill/gen3; cd $R; mkdir -p runs logs
log() { echo "$(date -u +%FT%TZ) $*" | tee -a $R/logs/run_g3.log; }
SB=~/h1distill/silverbot-84ab3ea; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt
W=${W:-$HOME/Documents/sts/az-gen3-train}; X=${X:-$HOME/Documents/sts/az-gen2-sweep}
export STS_OOC_HEART1_WING_BOOTS_COUNTER=1
DSHA=8aac69b65f90ef925fa9d1affa59f0c82edb08205a28de04ccb1e65b4989ffd2
[ "$(sha256sum $W/tools/heart1/distill.py | cut -c1-64)" = $DSHA ] || { log "FATAL distill.py sha mismatch in $W"; exit 1; }

# 1. rows: verify inputs, calibrate on non-exploration training folds, write the no-exploration-value copy
if [ ! -f $R/logs/calibrate.done ]; then
  (cd $R/rows_new && sha256sum -c --quiet ../rows_new.sha256) || { log "FATAL rows_new sha"; exit 1; }
  (cd ~/h1distill/gen2/vtargets/rows && sha256sum -c --quiet $R/gen2_vtargets_rows.sha256) || { log "FATAL old rows sha"; exit 1; }
  rm -rf $R/rows $R/rows_noev
  nice python3 $R/tools/calibrate_g3.py $R/rows $R/rows_new ~/h1distill/gen2/vtargets/rows --noev $R/rows_noev > $R/logs/calibration.json || exit 1
  n1=$(ls $R/rows | wc -l); n2=$(ls $R/rows_noev | wc -l); log "calibrated: rows $n1 noev $n2 $(cat $R/logs/calibration.json)"
  [ $n1 = 5760 ] && [ $n2 = 5760 ] || { log "FATAL expected 5760 files"; exit 1; }
  touch $R/logs/calibrate.done
fi

run() { n=$1; d=$2; shift 2; mkdir -p $R/runs/$n; grep -q "^EXIT 0" $R/runs/$n/train.log 2>/dev/null && return
  ( cd $W; { echo "sha $(git rev-parse HEAD) distill.py sha256 $(sha256sum tools/heart1/distill.py | cut -c1-64)"; echo "rows $d args $*"; } > $R/runs/$n/train.log
    /usr/bin/time -f "real %e user %U sys %S maxrss_kb %M" nice -n 10 python3 tools/heart1/distill.py $SB $R/runs/$n \
      --data $(ls $R/$d/*.gz) --trim-map --extra-inputs --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3 \
      --pack --val-at-end --compact --threads 1 --workers 4 --dim 64 --layers 2 --mult 4 --heads 4 \
      "$@" >> $R/runs/$n/train.log 2>&1 < /dev/null
    echo "EXIT $?" >> $R/runs/$n/train.log ); log "run $n $(tail -1 $R/runs/$n/train.log)"; }
FT="--lr 1e-4 --anchor-weight 0.3 --value-weight 0.3 --value-k 32 --init $SEL"
NS="--value-target-field nstep_v_cal --value-teacher-alpha 1"

# 2. three arms, seed 0
run G3_z rows $FT --seed 0
run G3_nstep rows $FT $NS --seed 0
run G3_nstep_noEv rows_noev $FT $NS --seed 0
# 3. reference evals on the same folds (lr 0, one epoch, no anchor)
EV() { echo "--lr 0 --epochs 1 --anchor-weight 0 --value-weight 1 --seed 0 --init $1 --anchor-ref $SEL"; }
run REF_student_sel rows $(EV $SEL)
run REF_gen2_pick rows $(EV $R/ref/gen2_pick/student.pt)
run REF_gen2_VT_nstep rows $(EV $R/ref/VT_nstep5_cal_l1/student.pt)
# 4. pick (PLAN rule) + seeds 1, 2
P=$(python3 $R/tools/pick.py $R/runs G3_) || { log "NO RUN QUALIFIES"; exit 0; }
log "pick $P"; echo $P > $R/logs/pick.txt
case $P in
  G3_z) A="rows $FT"; ;;
  G3_nstep) A="rows $FT $NS"; ;;
  G3_nstep_noEv) A="rows_noev $FT $NS"; ;;
esac
run ${P}_s1 $A --seed 1
run ${P}_s2 $A --seed 2
# 5. export + native parity of the pick (seed 0) on gen 1's 400 parity records
mkdir -p $R/export $R/parity; [ -f $R/parity/records.jsonl ] || cp ~/h1distill/gen2/parity/records.jsonl $R/parity/
( cd $X && OMP_NUM_THREADS=2 nice python3 tools/heart1/export_heart1_weights.py $R/runs/$P/student.pt $R/export/$P.bin \
    --allow-other-checkpoint --n-heads 4 --trim-map 2>&1 | grep -o "export sha256 .*" | tee $R/parity/RESULTS.txt
  OMP_NUM_THREADS=2 nice python3 tools/heart1/student_inputs.py score $SB $R/runs/$P/student.pt $R/parity/records.jsonl $R/parity/torch-$P.jsonl --trim-map > /dev/null 2>&1
  ./build-parity/one_combat heart1score $R/export/$P.bin $R/parity/records.jsonl $R/parity/native-$P.jsonl > /dev/null 2>&1 )
python3 - $R/parity/torch-$P.jsonl $R/parity/native-$P.jsonl $P <<'PY' | tee -a $R/parity/RESULTS.txt
import json,sys
t=[json.loads(l) for l in open(sys.argv[1])]; n=[json.loads(l) for l in open(sys.argv[2])]
assert len(t)==len(n); ml=mv=0; nl=0; am=0
for a,b in zip(t,n):
    assert len(a["logits"])==len(b["logits"]); nl+=len(a["logits"])
    ml=max(ml,max(abs(x-y) for x,y in zip(a["logits"],b["logits"]))); mv=max(mv,abs(a["value"]-b["value"]))
    am+=max(range(len(a["logits"])),key=a["logits"].__getitem__)!=b.get("argmax")
print(f"{sys.argv[3]} records {len(t)} logits {nl} max|dlogit| {ml:.3g} max|dvalue| {mv:.3g} argmax mismatches {am}")
PY
python3 $R/tools/summarize_g3.py $R > $R/results.md
log "G3 DONE"
