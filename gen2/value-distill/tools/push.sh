#!/bin/bash
# copy finished value-distill runs, exports and parity to the data branch and push (no force)
set -eu
V=~/h1distill/gen2/vdistill; D=~/Documents/sts/az-gen2-data/gen2/value-distill; mkdir -p $D/runs $D/weights $D/parity $D/tools
for r in $V/runs/*/; do n=$(basename $r); [ -f $r/summary.json ] || continue; mkdir -p $D/runs/$n; cp $r/train.log $r/summary.json $D/runs/$n/; [ -f $r/mono.txt ] && cp $r/mono.txt $D/runs/$n/; true; done
for b in $V/export/*.bin; do n=$(basename $b .bin); mkdir -p $D/weights/$n; cp $b $D/weights/$n/student.bin; cp $V/runs/$n/student.pt $D/weights/$n/; done
cp $V/parity/* $D/parity/; cp $V/parity.txt $D/parity/RESULTS.txt; (cd $D/parity && rm -f SHA256SUMS && sha256sum *.jsonl > SHA256SUMS); (cd $D/weights && sha256sum */* > SHA256SUMS)
cp $V/run_vd.sh $V/run_vd2.sh $V/export_parity.sh $V/push.sh $V/run_vd.log $D/tools/
cd ~/Documents/sts/az-gen2-data; git fetch -q origin claude/az-gen2-data; git rebase -q origin/claude/az-gen2-data 2>/dev/null || true
git add gen2/value-distill; git commit -q -m "$1

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git rebase -q origin/claude/az-gen2-data; git push -q -u origin claude/az-gen2-data; git log -1 --format=%H
