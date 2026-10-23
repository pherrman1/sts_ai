#!/bin/bash
# sweep FOLD: fine-tune grid on one seed fold, selection by inner validation only
cd /home/user/sts_ai
B=selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
SHA=ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b
F=$1
for lr in 1e-4 3e-4; do for l2 in 1 10 100; do for old in 0 0.25; do
  O=/home/user/work/ft/$F-lr$lr-l2$l2-old$old
  [ -d $O ] && continue
  if [ $old = 0 ]; then OLD=""; else OLD="--old /home/user/work/old.npz --old-share $old"; fi
  python3 tools/ctm_finetune.py train --base $B --base-sha $SHA --new /home/user/work/new.npz $OLD --seeds $F \
    --epochs 12 --lr $lr --l2sp $l2 --l2sp-hp $l2 --threads 2 --out $O > $O.log 2>&1
done; done; done
echo SWEEP_DONE
