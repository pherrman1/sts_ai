#!/bin/bash
# §470: score Stage 1 rows with the uncalibrated Lizard candidate (same call as run_regate.sh, candidate arm).
set -eu
G=/root/regate; C=/root/calib470; M=$G/ctm/candidate-pathb-a20-lizard.json
export OMP_NUM_THREADS=1
cd /root/w458test
for s in "$@"; do
  STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$M STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $M | cut -d' ' -f1) \
    $G/one_combat ctmscorerows $C/rows/$s.jsonl $C/scores/$s.cand.csv $G/ctm/FAST4L.native $G/ctm/STD2.native 1 2> $C/scores/$s.cand.log &
done
wait; tail -n1 $C/scores/*.cand.log
