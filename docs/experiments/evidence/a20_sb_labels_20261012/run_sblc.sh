#!/usr/bin/env bash
T=/tmp/claude-0/-home-user-sts-ai/b94b232e-4edc-561a-9463-dedf147e0ad5/scratchpad/train
cd /home/user/sts_ai
for cfg in "SBLC 1" "SBLCF 0"; do
  set -- $cfg
  STRAT_DEVICE=cpu STRAT_TOK_COMPILE=0 OMP_NUM_THREADS=4 STRAT_LABEL_SCALE=floor STRAT_Q_TARGET=fallback_centered STRAT_SPLIT_LOAD=$T/split_sbl.json STRAT_INIT_CKPT=/tmp/claude-0/v4final.pt STRAT_INIT_REUSE_NORM=1 STRAT_Q_ONLY=$2 STRAT_EPOCHS=30 STRAT_PATIENCE=30 STRAT_SELECT_METRIC=q_top1 python3 train_strategic_tok.py $T/sbl_a20.csv $T/$1 > $T/$1.log 2>&1
  echo TRAIN_EXIT $? >> $T/$1.log
done
