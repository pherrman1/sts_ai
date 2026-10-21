#!/bin/bash
# Cap check (running) -> candidate seed reruns only (d128/L2 seeds and 40-cap architecture reruns skipped) -> Stage T.
set -u
cd ~/h1distill/gen2
G=sweep; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; H1=$HOME/h1distill/gen2/heart1/heart1.pt
log() { echo "$(date -u +%FT%TZ) $*"; }
args_of() { grep "^args " $G/$1/train.log | cut -c6- ; }
selkl() { python3 -c "import json,sys;d=json.load(open('$G/$1/summary.json'));h=[x for x in d['history'] if x['epoch']==d['selected_epoch']][0];print(h['select']['kl'])"; }
ran() { python3 -c "import json;print(json.load(open('$G/$1/summary.json'))['epochs_run'])"; }
best=S_d64L2_lr1e-4_a0.3_v0.3_s0; C40=S_d64L2_lr1e-4_a0.3_v0.3_ep40_s0
until grep -q "^EXIT" $G/$C40/train.log 2>/dev/null; do sleep 30; done
grep -q "^EXIT 0" $G/$C40/train.log || { log "cap check failed"; exit 1; }
k20=$(selkl $best); k40=$(selkl $C40)
use40=$(python3 -c "print(1 if $k40 < $k20 - 0.002 else 0)"); log "cap check: sel KL 20-cap $k20, 40-cap $k40 (ran $(ran $C40) epochs) -> use40=$use40"
: > seeds.jobs; a=$(args_of $best)
for s in 1 2; do
  if [ $use40 = 1 ]; then echo "${best%_s0}_ep40_s$s ${a/--seed 0/--seed $s} --epochs 40" >> seeds.jobs
  else echo "${best%_s0}_s$s ${a/--seed 0/--seed $s}" >> seeds.jobs; fi
done
cut -c1-110 seeds.jobs
./queue.sh seeds.jobs > queue-seeds.log 2>&1
log "stage S done"
# Stage T1: heart1 fine-tune (own size, untrimmed, lr 1e-4, anchor to heart1); bs 256, falling back on CUDA OOM
T1=""
for bs in 256 128 64; do
  n=T1_heart1_lr1e-4_a1_v1_bs${bs}_s0
  grep -q "^EXIT 0" $G/$n/train.log 2>/dev/null || ./runT.sh $n gen2_files.txt --dim 256 --layers 4 --mult 4 --heads 8 \
     --bs $bs --lr 1e-4 --anchor-weight 1 --value-weight 1 --seed 0 --init $H1 < /dev/null
  if grep -q "^EXIT 0" $G/$n/train.log; then T1=$n; break; fi
  grep -q "OutOfMemoryError" $G/$n/train.log || { log "T1 failed (not OOM): $n"; exit 1; }
  log "T1 OOM at bs $bs"
done
[ -n "$T1" ] || exit 1; log "teacher $T1"
# Stage T2: label gen2 rows + the student_sel distillation set with the fine-tuned teacher (untrimmed, bf16)
if [ ! -f teacher_rows.done ]; then
  STS_HEART1_TOOLS=$HOME/Documents/sts/az-gen2-sweep/tools/heart1 nice -n 10 python3 tools/label_teacher.py \
    ~/h1distill/silverbot-84ab3ea $G/$T1/student.pt teacher_rows --bs 32 --amp \
    --data $(cat gen2_files.txt orig_files.txt) > label.log 2>&1 && touch teacher_rows.done || { log "labeling failed"; exit 1; }
fi
ls teacher_rows/*.gz > teacher_files.txt
# Stage T3: d64/L2 student from student_sel on teacher logits + z
T3=T3_distill_d64L2_lr3e-4_a0_v1_s0
grep -q "^EXIT 0" $G/$T3/train.log 2>/dev/null || ./runT.sh $T3 teacher_files.txt --dim 64 --layers 2 --mult 4 --heads 4 --trim-map \
   --bs 256 --lr 3e-4 --anchor-weight 0 --value-weight 1 --seed 0 --init $SEL < /dev/null
grep -q "^EXIT 0" $G/$T3/train.log || { log "T3 failed"; exit 1; }
# T3 scored on Stage S's data and folds (pi' targets): one epoch at lr 0 = the T3 student unchanged
E=E_T3_on_gen2
grep -q "^EXIT 0" $G/$E/train.log 2>/dev/null || ./run.sh $E --dim 64 --layers 2 --mult 4 --heads 4 --lr 0 --epochs 1 \
   --anchor-weight 0 --value-weight 1 --seed 0 --init $G/$T3/student.pt --anchor-ref $SEL < /dev/null
log "PIPELINE DONE"
