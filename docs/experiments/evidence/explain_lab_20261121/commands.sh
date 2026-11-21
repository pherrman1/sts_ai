#!/bin/bash
S=/tmp/claude-0/-home-user/f0fe8bc0-c121-5e8f-ae12-5dc718ad8abd/scratchpad
E=/home/user/sts_ai/tools/az_bench/explain.py
L=/home/user/sts_ai/tools/az_bench/explain_lab.py
cd $S
C="--ckpt ckpt_895975.pt --replay gen/replay --threads 4 --seed 0"
python3 $E $C --mode survey --states 60 --out ev/survey.json > ev/survey.log 2>&1
python3 $E $C --mode table --states 24 --out ev/table.json > ev/table.log 2>&1
python3 $E $C --mode pairs --out ev/pairs_895975.json > ev/pairs_895975.log 2>&1
python3 $E --ckpt ckpt_791357.pt --replay gen/replay --threads 4 --seed 0 --mode pairs --out ev/pairs_791357.json > ev/pairs_791357.log 2>&1
python3 $L $C --mode coverage --out ev/coverage.json > ev/coverage.log 2>&1
python3 $L $C --mode design --out ev/design.json > ev/design.log 2>&1
python3 $L $C --mode lens --out ev/lens.json > ev/lens.log 2>&1
python3 $L $C --mode patch --limit 80 --out ev/patch.json > ev/patch.log 2>&1
python3 $L $C --mode calibration --out ev/calibration.json > ev/calibration.log 2>&1
python3 $L $C --mode shapley --states 30 --out ev/shapley.json > ev/shapley.log 2>&1
python3 $L $C --mode counterfactual --states 40 --out ev/counterfactual.json > ev/counterfactual.log 2>&1
python3 $L $C --mode interact --states 12 --out ev/interact.json > ev/interact.log 2>&1
python3 $L $C --ckpt2 ckpt_791357.pt --mode probe --out ev/probe.json > ev/probe.log 2>&1
python3 $L $C --ckpt2 ckpt_791357.pt --mode faithful --states 30 --perms 32 --exact-limit 1024 --out ev/faithful.json > ev/faithful.log 2>&1
echo done > ev/DONE
