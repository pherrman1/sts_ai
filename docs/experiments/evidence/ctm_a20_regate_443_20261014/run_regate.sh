#!/bin/bash
# §443 Stage 4 Step 3 re-gate: frozen gate3a.py (25f7dc00) on ALL rows of the fresh Stage 4 corpus (no TEST filter:
# PREREG-REGATE.md Step 3), binary e59727ca (= Stage 3a, built at 40db7d62). Candidate = Step 1b Lizard candidate
# (FAST4L/STD2/manifest 704f2a58) with LIZARD=1; production call unchanged from run_gate3a.sh. No seeds are driven.
set -u
G=/root/regate; cd $G
OC=$G/one_combat M=$G/ctm/candidate-pathb-a20-lizard.json FAST=$G/ctm/FAST4L.native STD=$G/ctm/STD2.native
stop() { echo "STOPPED_AT $1"; exit 1; }
export OMP_NUM_THREADS=1; unset STS_CTM_PINS STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
[ "$(sha256sum < gate3a.py | cut -c1-64)" = 25f7dc0020b2b6874e55f29b4a508ac38bd245e94b5372e0fe93d07751838bd7 ] || stop script_sha
[ "$(sha256sum < $OC | cut -c1-64)" = e59727cae6b5d2b77a614e18ca9a16c541158ecbdddfa1a830cfa0bd14abc173 ] || stop binary_sha
sha256sum -c ctm.sha256 >/dev/null || stop ctm_sha
cd /root/w458test || stop repo   # ctmscorerows loads production models relative to the 40db7d62 checkout
for s in none lizard_fairy lizard_brew; do f=$G/rows/$s.jsonl
  python3 $G/gate3a.py clamp $f $G/rows-clamped/$s.jsonl >> $G/logs/clamp.log || stop clamp_$s
  env -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256 $OC ctmscorerows $G/rows-clamped/$s.jsonl $G/scores/$s.prod.csv 2> $G/logs/$s.prod.log &
  STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$M STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $M | cut -d' ' -f1) \
    $OC ctmscorerows $f $G/scores/$s.cand.csv $FAST $STD 1 2> $G/logs/$s.cand.log &
  wait
  grep -q "research candidate pathb-a20" $G/logs/$s.cand.log || stop cand_identity_$s
  ! grep -q "research candidate" $G/logs/$s.prod.log || stop prod_identity_$s
  echo "$s $(tail -1 $G/logs/$s.prod.log) | $(tail -1 $G/logs/$s.cand.log) | rows $(wc -l < $f)"
done
python3 $G/gate3a.py compare --prod $G/scores/none.prod.csv --cand $G/scores/none.cand.csv --label main_fresh --role gate --out $G/results/main_fresh.json > $G/logs/main_fresh.summary.json || stop compare_main
for s in lizard_fairy lizard_brew; do
  python3 $G/gate3a.py compare --prod $G/scores/$s.prod.csv --cand $G/scores/$s.cand.csv --label ${s}_fresh --out $G/results/${s}_fresh.json > $G/logs/${s}_fresh.summary.json || stop compare_$s
done
cat $G/logs/main_fresh.summary.json
echo ALL_DONE
