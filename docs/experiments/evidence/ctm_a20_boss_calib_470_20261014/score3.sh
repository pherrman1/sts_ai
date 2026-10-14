#!/bin/bash
# §470 checks 2-3: calibrated candidate (new binary 105d1f59) on old TEST rows and on the fresh Stage 4 rows
# (unchanged rows from /root/regate/rows); gate3a 25f7dc00 against the re-gate's frozen production scores.
set -eu
C=/root/calib470 G=/root/regate M=/root/calib470/ctm/candidate-pathb-a20-lizard-boss470.json
export OMP_NUM_THREADS=1; cd /home/user/sts_ai
[ "$(sha256sum < $G/gate3a.py | cut -c1-64)" = 25f7dc0020b2b6874e55f29b4a508ac38bd245e94b5372e0fe93d07751838bd7 ]
run() { STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$M STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $M | cut -d' ' -f1) \
  $C/one_combat ctmscorerows $1 $2 selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native selfplay/models/combat_transition_near_full_escape_pathb_a20.native 1 2> $2.log; }
mkdir -p $C/fresh $C/results
run $C/rows/test.jsonl $C/scores/test.calib.csv &
for s in none lizard_fairy lizard_brew; do run $G/rows/$s.jsonl $C/fresh/$s.calib.csv & done
wait; tail -qn1 $C/scores/test.calib.csv.log $C/fresh/*.calib.csv.log
python3 $G/gate3a.py compare --prod $G/scores/none.prod.csv --cand $C/fresh/none.calib.csv --label main_fresh_boss470 --role gate --out $C/results/main_fresh_boss470.json > $C/results/main_fresh_boss470.summary.json
for s in lizard_fairy lizard_brew; do
  python3 $G/gate3a.py compare --prod $G/scores/$s.prod.csv --cand $C/fresh/$s.calib.csv --label ${s}_fresh_boss470 --out $C/results/${s}_fresh_boss470.json > $C/results/${s}_fresh_boss470.summary.json
done
cat $C/results/main_fresh_boss470.summary.json; echo ALL_DONE
