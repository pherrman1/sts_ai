#!/bin/bash
# usage: gates.sh SCRATCH ALPHA CAND.bin  -- held-out expert + bot-state scoring and gates
set -e
S=$1; A=$2; BIN=$3; D=$S/train/data_${PFX:-}a$A; G=$S/train/gates_${PFX:-}a$A; mkdir -p $G
python3 -c "
import glob,gzip,sys
with open('$G/exp_val.jsonl','w') as o:
    for f in sorted(glob.glob('$D/exp-*.capture.jsonl.gz')):
        if int(f.split('exp-')[1].split('.')[0])%8!=7: continue
        for l in gzip.open(f,'rt'): o.write(l)
"
OC=/home/user/sts_ai/build/linux-gcc-release/one_combat
cd /home/user/sts_ai
$OC heart1score $S/train/student_sel.bin $G/exp_val.jsonl $G/base_exp.jsonl | tail -1
$OC heart1score $BIN $G/exp_val.jsonl $G/cand_exp.jsonl | tail -1
$OC heart1score $BIN $S/train/bot_records.jsonl $G/cand_bot.jsonl | tail -1
python3 $S/tools/gates.py $D $G/base_exp.jsonl $G/cand_exp.jsonl $S/train/bot_records.jsonl $S/train/bot_scores.jsonl $G/cand_bot.jsonl $G/gates.json
