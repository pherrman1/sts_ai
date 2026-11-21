#!/bin/bash
S=/tmp/claude-0/-home-user/f0fe8bc0-c121-5e8f-ae12-5dc718ad8abd/scratchpad
E=/home/user/sts_ai/tools/az_bench/explain.py
L=/home/user/sts_ai/tools/az_bench/explain_lab.py
while kill -0 3000 2>/dev/null; do sleep 20; done
cd $S
ls gen256/replay > ev256/replay_files.txt 2>&1
C="--ckpt ckpt_895975.pt --replay gen256/replay --threads 2 --seed 0"
python3 $L $C --mode calibration --out ev256/calibration.json > ev256/calibration.log 2>&1
python3 $L $C --mode coverage --out ev256/coverage.json > ev256/coverage.log 2>&1
python3 $E $C --mode pairs --out ev256/pairs_895975.json > ev256/pairs_895975.log 2>&1
python3 $L $C --ckpt2 ckpt_791357.pt --mode probe --out ev256/probe.json > ev256/probe.log 2>&1
python3 $E $C --mode survey --states 60 --out ev256/survey.json > ev256/survey.log 2>&1
python3 $L $C --mode design --out ev256/design.json > ev256/design.log 2>&1
echo done > ev256/DONE
