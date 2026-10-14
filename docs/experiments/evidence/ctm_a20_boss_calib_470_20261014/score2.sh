#!/bin/bash
# §470 check 1: new binary; validation rows with the calibrated manifest and (no-change check) the old one.
set -eu
C=/root/calib470; export OMP_NUM_THREADS=1; cd /home/user/sts_ai
run() { STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$2 STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $2 | cut -d' ' -f1) \
  $C/one_combat ctmscorerows $C/rows/$1.jsonl $C/scores/$1.$3.csv selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native selfplay/models/combat_transition_near_full_escape_pathb_a20.native 1 2> $C/scores/$1.$3.log; }
run validation $C/ctm/candidate-pathb-a20-lizard-boss470.json calib &
run validation /root/regate/ctm/candidate-pathb-a20-lizard.json newbin &
wait; tail -qn1 $C/scores/validation.calib.log $C/scores/validation.newbin.log
cmp $C/scores/validation.newbin.csv $C/scores/validation.cand.csv && echo NOCHANGE_OK
