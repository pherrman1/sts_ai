#!/bin/bash
cd ~/h1distill/gen2
until grep -q "BENCH DONE" bench.log; do sleep 10; done
B="--dim 64 --layers 2 --mult 4 --heads 4 --anchor-weight 1 --value-weight 1 --seed 0 --init $HOME/h1distill/E_sel/E_d64_sel_xin/student.pt --stop-after 1"
run() { n=$1; shift; [ -f sweep/bench_$n/summary.json ] || ./run.sh bench_$n $B "$@" < /dev/null; }
run d_pack --lr 3e-4 --pack
run e_pack_valend --lr 3e-4 --pack --val-at-end
run f_pack_bs1024 --lr 6e-4 --pack --bs 1024
echo BENCH2 DONE
