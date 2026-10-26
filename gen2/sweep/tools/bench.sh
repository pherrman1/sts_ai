#!/bin/bash
cd ~/h1distill/gen2
B="--dim 64 --layers 2 --mult 4 --heads 4 --anchor-weight 1 --value-weight 1 --seed 0 --init $HOME/h1distill/E_sel/E_d64_sel_xin/student.pt --stop-after 1"
run() { n=$1; shift; [ -f sweep/bench_$n/summary.json ] || ./run.sh bench_$n $B "$@" < /dev/null; }
run base --lr 3e-4
run c_valend --lr 3e-4 --val-at-end
run a_k16 --lr 3e-4 --value-k 16
run a_k32 --lr 3e-4 --value-k 32
run b_bs1024 --lr 6e-4 --bs 1024
echo BENCH DONE
