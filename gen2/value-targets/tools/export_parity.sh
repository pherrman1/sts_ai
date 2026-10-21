#!/bin/bash
# usage: export_parity.sh RUN  -- export runs/RUN/student.pt (--n-heads 4 --trim-map) and run native parity on gen 1's 400 records
set -eu
cd ~/Documents/sts/az-gen2-sweep
V=~/h1distill/gen2/vtargets; n=$1; P=$V/parity; mkdir -p $P $V/export; export STS_OOC_HEART1_WING_BOOTS_COUNTER=1 OMP_NUM_THREADS=2
[ -f $P/records.jsonl ] || cp ~/h1distill/gen2/parity/records.jsonl $P/
nice python3 tools/heart1/export_heart1_weights.py $V/runs/$n/student.pt $V/export/$n.bin --allow-other-checkpoint --n-heads 4 --trim-map 2>&1 | grep -o "export sha256 .*"
nice python3 tools/heart1/student_inputs.py score ~/h1distill/silverbot-84ab3ea $V/runs/$n/student.pt $P/records.jsonl $P/torch-$n.jsonl --trim-map > /dev/null 2>&1
./build-parity/one_combat heart1score $V/export/$n.bin $P/records.jsonl $P/native-$n.jsonl > /dev/null 2>&1
python3 - $P/torch-$n.jsonl $P/native-$n.jsonl $n <<'PY'
import json,sys
t=[json.loads(l) for l in open(sys.argv[1])]; n=[json.loads(l) for l in open(sys.argv[2])]
assert len(t)==len(n); ml=mv=0; nl=0; am=0
for a,b in zip(t,n):
    assert len(a["logits"])==len(b["logits"]); nl+=len(a["logits"])
    ml=max(ml,max(abs(x-y) for x,y in zip(a["logits"],b["logits"]))); mv=max(mv,abs(a["value"]-b["value"]))
    am+=max(range(len(a["logits"])),key=a["logits"].__getitem__)!=b.get("argmax")
print(f"{sys.argv[3]} records {len(t)} logits {nl} max|dlogit| {ml:.3g} max|dvalue| {mv:.3g} argmax mismatches {am}")
PY
