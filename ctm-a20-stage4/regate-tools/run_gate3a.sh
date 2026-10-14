#!/bin/bash
# §443 Stage 3a offline gate. Frozen inputs in PREREG-FROZEN.txt. No seeds are driven (ctmscorerows reads rows only).
set -u
WT=/home/philippherrmann/Documents/sts/wt-ctm-a20-docfix; cd $WT
G=/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/gate3a; R=/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/run
OC=$WT/build/linux-gcc-release/one_combat; M=$R/candidate-pathb-a20-escape.json FAST=$R/FAST1-escape.native STD=$R/STD1-escape.native
PY="python3 -P -E"
stop() { echo "STOPPED_AT $1"; exit 1; }
export OMP_NUM_THREADS=1; unset STS_CTM_PINS STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
[ "$(git rev-parse HEAD)" = 40db7d62b89e6d2ef52c91cda167e7f0e698e42a ] && [ -z "$(git status --porcelain)" ] || stop checkout
[ "$(sha256sum < $G/gate3a.py | cut -c1-64)" = 25f7dc0020b2b6874e55f29b4a508ac38bd245e94b5372e0fe93d07751838bd7 ] || stop script_sha
$PY $G/offline_ab_compare_418.py extract --union $R/union --out $G > $G/logs/extract.log 2>&1 || stop extract
mkdir -p $G/rows-clamped
for f in $G/rows/*.jsonl; do s=$(basename $f .jsonl)
  $PY $G/gate3a.py clamp $f $G/rows-clamped/$s.jsonl >> $G/logs/clamp.log || stop clamp_$s
  test ! -e $G/scores/$s.prod.csv && test ! -e $G/scores/$s.cand.csv || stop exists_$s
  env -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256 $OC ctmscorerows $G/rows-clamped/$s.jsonl $G/scores/$s.prod.csv 2> $G/logs/$s.prod.log &
  STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$(realpath $M) STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $M | cut -d' ' -f1) \
    $OC ctmscorerows $f $G/scores/$s.cand.csv $FAST $STD 0 2> $G/logs/$s.cand.log &
  wait
  grep -q "research candidate pathb-a20" $G/logs/$s.cand.log || stop cand_identity_$s
  ! grep -q "research candidate" $G/logs/$s.prod.log || stop prod_identity_$s
  echo "$s $(tail -1 $G/logs/$s.prod.log) | $(tail -1 $G/logs/$s.cand.log) | rows $(wc -l < $f)"
done
$PY $G/gate3a.py compare --prod $G/scores/none.prod.csv --cand $G/scores/none.cand.csv --label main_test --role gate --out $G/results/main_test.json > $G/logs/main_test.summary.json || stop compare_main
for s in ritual_writhing high_maxhp lizard_fairy lizard_brew; do
  $PY $G/gate3a.py compare --prod $G/scores/$s.prod.csv --cand $G/scores/$s.cand.csv --label ${s}_test --out $G/results/${s}_test.json > $G/logs/${s}_test.summary.json || stop compare_$s
done
cat $G/logs/main_test.summary.json
echo ALL_DONE
