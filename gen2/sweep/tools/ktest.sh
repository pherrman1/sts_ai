#!/bin/bash
cd ~/h1distill/gen2
B="--dim 64 --layers 2 --mult 4 --heads 4 --lr 3e-4 --anchor-weight 1 --value-weight 1 --seed 0 --init $HOME/h1distill/E_sel/E_d64_sel_xin/student.pt"
for k in 16 32; do n=K_d64L2_lr3e-4_a1_v1_k${k}_s0; [ -f sweep/$n/summary.json ] || ./run.sh $n $B --value-k $k < /dev/null; done
echo KTEST DONE
