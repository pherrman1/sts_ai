#!/bin/bash
# AZ gen 2: everything after the grid, unattended. Each step skips work already finished (EXIT 0 in its log).
set -u
cd ~/h1distill/gen2
G=sweep; SEL=$HOME/h1distill/E_sel/E_d64_sel_xin/student.pt; H1=$HOME/h1distill/gen2/heart1/heart1.pt
log() { echo "$(date -u +%FT%TZ) $*"; }
until grep -q "QUEUE DONE grid.jobs" queue-grid.log; do sleep 30; done
best=$(python3 tools/pick.py $G S_d64L2_) || exit 1; log "best grid point $best"
lr=$(sed -E 's/.*_lr([^_]+)_.*/\1/' <<<"$best"); vw=$(sed -E 's/.*_v([^_]+)_.*/\1/' <<<"$best")
args_of() { grep "^args " $G/$1/train.log | cut -c6- ; }
: > arch.jobs
for spec in "96 2" "128 2" "64 3"; do set -- $spec
  echo "A_d$1L$2_lr${lr}_a0_v${vw}_s0 --dim $1 --layers $2 --mult 4 --heads 4 --lr $lr --anchor-weight 0 --value-weight $vw --seed 0 --anchor-ref $SEL" >> arch.jobs
done
./queue.sh arch.jobs > queue-arch.log 2>&1
barch=$(python3 tools/pick.py $G A_) || exit 1; log "best architecture $barch"
: > seeds.jobs
for r in $best $barch; do a=$(args_of $r); for s in 1 2; do
  echo "${r%_s0}_s$s ${a/--seed 0/--seed $s}" >> seeds.jobs; done; done
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
