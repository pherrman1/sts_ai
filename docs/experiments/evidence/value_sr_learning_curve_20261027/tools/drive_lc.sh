#!/bin/bash
# One-command driver for the learning curve (../PLAN.md) on Philipp's PC, without a Claude session:
#   setsid nohup gen2/value-sr-lc/tools/drive_lc.sh > ~/h1distill/gen2/valuesrlc/drive.log 2>&1 &
# from a clone of claude/az-gen2-data (any checkout of this commit or later). It checks the GPU is idle, checks that
# the export reproduces SR_crn_r2_s2_ep20 (sha256 28523fb5...), runs smoke, main (PAR=2) and split, and after each
# phase exports the pick_epoch.py choice of every run and pushes ONLY gen2/value-sr-lc/{runs,weights}/ files.
# REPO = an sts_ai checkout with tools/heart1/export_heart1_weights.py (default ~/Documents/sts/az-gen2-vdistill).
set -u
T=$(cd "$(dirname "$0")" && pwd); G=$(cd $T/../../.. && pwd); R=~/h1distill/gen2/valuesrlc; mkdir -p $R
REPO=${REPO:-~/Documents/sts/az-gen2-vdistill}; EXP="python3 $REPO/tools/heart1/export_heart1_weights.py"
log() { echo "$(date -u +%FT%TZ) drive $*" | tee -a $R/run_lc.log; }
used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
[ "${used:-0}" -lt 4000 ] || { log "GPU busy (${used} MiB used), not starting"; exit 1; }
ref=~/h1distill/gen2/valuesrcrn/runs/SR_crn_r2_s2/student_ep20.pt
$EXP $ref $R/ref.bin --allow-other-checkpoint --n-heads 4 --trim-map > /dev/null || { log "export failed"; exit 1; }
[ "$(sha256sum $R/ref.bin | cut -c1-8)" = 28523fb5 ] || { log "export does not reproduce 28523fb5, stopping"; exit 1; }
publish() {
  cd $G; for n in "$@"; do d=$R/runs/$n; grep -q "^EXIT 0" $d/train.log 2>/dev/null || { log "$n not finished"; continue; }
    python3 $T/../../value-sr-crn/tools/pick_epoch.py $d/summary.json > $d/pick.json
    e=$(python3 -c "import json,sys; p=json.load(open(sys.argv[1])); print(p['ranking'] or max(p['curve'], key=lambda r: r[1])[0])" $d/pick.json)
    mkdir -p gen2/value-sr-lc/runs/$n gen2/value-sr-lc/weights/${n}_ep$e
    cp $d/summary.json $d/train.log $d/pick.json gen2/value-sr-lc/runs/$n/
    $EXP $d/student_ep$e.pt gen2/value-sr-lc/weights/${n}_ep$e/student.bin --allow-other-checkpoint --n-heads 4 --trim-map > /dev/null
    git add gen2/value-sr-lc/runs/$n gen2/value-sr-lc/weights/${n}_ep$e; log "$n ranking epoch $e"; done
  bad=$(git diff --cached --name-only | grep -v '^gen2/value-sr-lc/' | head -1)
  [ -z "$bad" ] || { log "staged file outside value-sr-lc ($bad), not committing"; git reset -q; return; }
  git commit -q -m "value-sr-lc: runs $* (pick_epoch choice exported)" && for i in 1 2 3; do
    git push -q origin HEAD:claude/az-gen2-data && { log "pushed $(git rev-parse --short HEAD)"; return; }
    git pull -q --no-rebase --no-edit origin claude/az-gen2-data; done; log "push failed"; }
$T/run_lc.sh smoke; grep -q "^EXIT 0" $R/runs/smoke_lc/train.log || { log "smoke failed"; exit 1; }
PAR=${PAR:-2} $T/run_lc.sh main; publish LC25_s1 LC25_s2 LC50_s1 LC50_s2
PAR=${PAR:-2} $T/run_lc.sh split; publish LC25rows_s1 LC25groups_s1
log "ALL DONE"
