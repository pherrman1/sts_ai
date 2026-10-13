#!/bin/bash
# §443 s23 Lizard packaging for pathb-a20 (PREREG-LIZARD.md bc116f03...). CPU only. origin/main tools + one_combat.
set -u
W=/home/philippherrmann/Documents/sts/wt-lizard-s23
cd $W; export PYTHONPATH=.
SHA=37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08
R=/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/run; O=/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/lizard-s23
OC=$W/build/linux-gcc-release/one_combat; LOG=$O/commands.log
STD1E=$R/STD1-escape.native FAST0=$R/FAST-export.native FAST1E=$R/FAST1-escape.native ESCPT=$R/capabilities/esc-fast-fit/escape.pt P12=$R/pins-12.json
MQ=docs/experiments/evidence/lizard_tail_mechanical_q_qualification_2026-09-25/mechanical_q_candidate.json
stop() { echo "STOPPED_AT $1 $(date -u +%FT%TZ)" | tee -a $LOG; exit 1; }
shas() { for f in "$@"; do [ -f "$f" ] && echo "    $(sha256sum "$f" | cut -d' ' -f1)  $f" >> $LOG || echo "    MISSING  $f" >> $LOG; done; }
# run NAME "inputs" "outputs" cmd... (stdout -> NAME.stdout, stderr -> NAME.stderr)
run() { n=$1 ins=$2 outs=$3; shift 3; for f in $outs; do [ ! -e "$f" ] || stop "exists_$(basename $f)"; done
  { echo "=== $n START $(date -u +%FT%TZ)"; echo "  cmd: $*"; echo "  env: STS_CTM_PINS=${STS_CTM_PINS:-} MANIFEST=${STS_CTM_RESEARCH_CANDIDATE_MANIFEST:-} MANIFEST_SHA256=${STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256:-}"; echo "  inputs:"; } >> $LOG; shas $ins
  "$@" > $O/$n.stdout 2> $O/$n.stderr; rc=$?
  { echo "  rc=$rc END $(date -u +%FT%TZ)"; echo "  outputs:"; } >> $LOG; shas $outs
  echo "=== $n rc=$rc"; [ $rc -eq 0 ] || { tail -5 $O/$n.stderr; stop $n; }; }
echo "CODE_SHA $(git rev-parse HEAD) one_combat $(sha256sum $OC | cut -d' ' -f1)" | tee $O/CODE_SHA.txt >> $LOG
[ "$(git rev-parse HEAD)" = "$SHA" ] || stop head; [ -z "$(git status --porcelain)" ] || stop dirty_tree
unset STS_CTM_PINS STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
# 1
run s1-std2 "$STD1E" "$O/STD2.native" python3 tools/ctm_capabilities.py writhing-ritual --artifact $STD1E --out $O/STD2.native
# 2
run s2-package "$FAST0 $MQ $P12" "$O/FAST0L.native" env STS_CTM_PINS=$P12 python3 tools/package_deepsets_lizard_artifact.py $FAST0 $MQ $O/FAST0L.native
# 3
run s3-stamp "$O/FAST0L.native $O/STD2.native" "$O/FAST1L.native" python3 tools/ctm_candidate.py stamp --artifact $O/FAST0L.native --control $O/STD2.native --out $O/FAST1L.native
# 4
run s4-escextend "$O/FAST1L.native $ESCPT" "$O/FAST2L.native" python3 tools/ctm_escape.py extend --artifact $O/FAST1L.native --checkpoint $ESCPT --out $O/FAST2L.native
run s4-payloadcheck "$O/FAST2L.native $FAST1E" "" python3 $O/payload_check.py $O/FAST2L.native $FAST1E
cp $O/s4-payloadcheck.stdout $O/step4-payload-check.txt
# 5
run s5-writhing "$O/FAST2L.native" "$O/FAST3L.native" python3 tools/ctm_capabilities.py writhing-ritual --artifact $O/FAST2L.native --out $O/FAST3L.native
run s5-manifest "$O/STD2.native $O/FAST3L.native" "$O/interim.json" python3 tools/ctm_candidate.py manifest --standard $O/STD2.native --fast $O/FAST3L.native --out $O/interim.json
cat $O/s5-manifest.stdout
export STS_CTM_RESEARCH_CANDIDATE_MANIFEST="$(realpath $O/interim.json)"; export STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256="$(sha256sum $O/interim.json | cut -d' ' -f1)"
# 6
for s in lizard_fairy lizard_brew none; do
  run s6-features-$s "$R/scope-$s/corpus.jsonl $O/FAST3L.native $O/STD2.native" "$O/features-$s.csv" $OC ctmlizardfeatures $R/scope-$s/corpus.jsonl $O/FAST3L.native $O/STD2.native $O/features-$s.csv
done
# 7
run s7-fit "$O/features-lizard_fairy.csv $O/features-lizard_brew.csv $O/features-none.csv" "" python3 tools/ctm_lizard.py fit --features $O/features-lizard_fairy.csv $O/features-lizard_brew.csv $O/features-none.csv --out $O/lizfit
shas $O/lizfit/*
run s7-extend "$O/FAST3L.native $O/lizfit/fit.json" "$O/FAST4L.native" python3 tools/ctm_lizard.py extend --artifact $O/FAST3L.native --fit $O/lizfit/fit.json --out $O/FAST4L.native --fast-r --brew --fairy
run s7-manifest "$O/STD2.native $O/FAST4L.native" "$O/candidate-pathb-a20-lizard.json" python3 tools/ctm_candidate.py manifest --standard $O/STD2.native --fast $O/FAST4L.native --out $O/candidate-pathb-a20-lizard.json
python3 $R/capabilities/hdr.py $O/STD2.native $O/FAST4L.native > $O/final-headers.txt
echo "ALL_DONE $(date -u +%FT%TZ)" | tee -a $LOG
