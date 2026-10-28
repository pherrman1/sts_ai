#!/usr/bin/env bash
# queue.sh LIST OUTDIR REPO RUN : run_probe.sh for each run id in LIST (skips finished), 4 parallel; set ARMS, ROOMS,
# ARMK, MAXACT in the environment. RUN holds one_combat, student_sel.bin and expert_runs.tar (as in §711).
LIST=$1 OUT=$2 REPO=$3 RUN=$4
cd "$(dirname "$0")"
xargs -P4 -I{} bash -c '[ -s "'$OUT'/{}/F-{}.done" ] || { rm -rf "'$OUT'/{}"; bash run_probe.sh '$REPO' '$RUN' "'$OUT'/{}" {}; }' < "$LIST"
echo QUEUE_DONE
