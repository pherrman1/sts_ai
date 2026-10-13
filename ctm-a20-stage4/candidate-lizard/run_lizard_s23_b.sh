#!/bin/bash
# §443 s23 Lizard packaging, continuation after the step-4 block. PREREG-LIZARD.md amended (sha256 d2ea9904...):
# step 4 = refit the fast escape on FAST1L exactly as chain B did (run_escape_a20.sh e3a-e3d); payload equality is diagnostic.
set -u
W=/home/philippherrmann/Documents/sts/wt-lizard-s23
cd $W; export PYTHONPATH=.
SHA=37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08
R=/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/run; O=/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/lizard-s23
OC=$W/build/linux-gcc-release/one_combat; LOG=$O/commands.log; CAP=$R/capabilities; G="python3 $CAP/gates.py"
FAST1E=$R/FAST1-escape.native
stop() { echo "STOPPED_AT $1 $(date -u +%FT%TZ)" | tee -a $LOG; exit 1; }
shas() { for f in "$@"; do [ -f "$f" ] && echo "    $(sha256sum "$f" | cut -d' ' -f1)  $f" >> $LOG || echo "    MISSING  $f" >> $LOG; done; }
run() { n=$1 ins=$2 outs=$3; shift 3; for f in $outs $O/$n.stdout $O/$n.stderr; do [ ! -e "$f" ] || stop "exists_$(basename $f)"; done
  { echo "=== $n START $(date -u +%FT%TZ)"; echo "  cmd: $*"; echo "  env: STS_CTM_PINS=${STS_CTM_PINS:-} MANIFEST=${STS_CTM_RESEARCH_CANDIDATE_MANIFEST:-} MANIFEST_SHA256=${STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256:-}"; echo "  inputs:"; } >> $LOG; shas $ins
  "$@" > $O/$n.stdout 2> $O/$n.stderr; rc=$?
  { echo "  rc=$rc END $(date -u +%FT%TZ)"; echo "  outputs:"; } >> $LOG; shas $outs
  echo "=== $n rc=$rc"; [ $rc -eq 0 ] || { tail -5 $O/$n.stderr; stop $n; }; }
usem() { export STS_CTM_RESEARCH_CANDIDATE_MANIFEST="$(realpath "$1")"; export STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256="$(sha256sum "$1" | cut -d' ' -f1)"; echo "usem $1 $STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256" | tee -a $LOG; }
echo "=== CONTINUATION (amended PREREG-LIZARD d2ea9904...) $(date -u +%FT%TZ) HEAD $(git rev-parse HEAD) one_combat $(sha256sum $OC | cut -d' ' -f1)" | tee -a $LOG
[ "$(git rev-parse HEAD)" = "$SHA" ] || stop head; [ -z "$(git status --porcelain)" ] || stop dirty_tree
unset STS_CTM_PINS STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
# reuse steps 1-3 (verify unchanged)
[ "$(sha256sum $O/STD2.native | cut -d' ' -f1)" = e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d ] || stop std2_changed
[ "$(sha256sum $O/FAST0L.native | cut -d' ' -f1)" = d8064294904a206668d844967e99a9c54b4f999204d3f0ef8019188bb81d4b7e ] || stop fast0l_changed
[ "$(sha256sum $O/FAST1L.native | cut -d' ' -f1)" = 6090417f25458907dfdcbfe1c6b128edf1406c8127028989d44dd5f845f0369f ] || stop fast1l_changed
# 4 (chain B e3a-e3d with FAST1L as base, STD2 as standard)
run s4b-manifest "$O/STD2.native $O/FAST1L.native" "$O/interim-fast1l.json" python3 tools/ctm_candidate.py manifest --standard $O/STD2.native --fast $O/FAST1L.native --out $O/interim-fast1l.json
usem $O/interim-fast1l.json
mkdir -p $O/esc-fast
run s4b-escfeatures "$R/union/corpus.jsonl $O/FAST1L.native" "$O/esc-fast/features.csv $O/esc-fast/features.f32" $OC ctmescapefeatures $R/union/corpus.jsonl $O/FAST1L.native $O/esc-fast/features
run s4b-escfit "$O/FAST1L.native $O/esc-fast/features.csv $O/esc-fast/features.f32" "$O/esc-fast-fit/escape.pt $O/esc-fast-fit/fit.json" python3 tools/ctm_escape.py fit --artifact $O/FAST1L.native --features $O/esc-fast/features --out $O/esc-fast-fit
$G escape-fit $O/s4b-escfit.stdout | tee -a $LOG; [ ${PIPESTATUS[0]} -eq 0 ] || stop gate_escape_nll
$G hpclasses-equal $CAP/esc-std-fit.stdout.json $O/s4b-escfit.stdout | tee -a $LOG; [ ${PIPESTATUS[0]} -eq 0 ] || stop gate_hpclasses
run s4b-escextend "$O/FAST1L.native $O/esc-fast-fit/escape.pt" "$O/FAST2L.native" python3 tools/ctm_escape.py extend --artifact $O/FAST1L.native --checkpoint $O/esc-fast-fit/escape.pt --out $O/FAST2L.native
# diagnostic (not a stop rule)
python3 $O/escape_diff.py $O/FAST2L.native $FAST1E > $O/step4-payload-check.txt 2>&1; echo "  step4 diagnostic rc=$?" >> $LOG; cat $O/step4-payload-check.txt | tee -a $LOG
unset STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
# 5
run s5-writhing "$O/FAST2L.native" "$O/FAST3L.native" python3 tools/ctm_capabilities.py writhing-ritual --artifact $O/FAST2L.native --out $O/FAST3L.native
run s5-manifest "$O/STD2.native $O/FAST3L.native" "$O/interim.json" python3 tools/ctm_candidate.py manifest --standard $O/STD2.native --fast $O/FAST3L.native --out $O/interim.json
cat $O/s5-manifest.stdout
usem $O/interim.json
# 6
for s in lizard_fairy lizard_brew none; do
  run s6-features-$s "$R/scope-$s/corpus.jsonl $O/FAST3L.native $O/STD2.native" "$O/features-$s.csv" $OC ctmlizardfeatures $R/scope-$s/corpus.jsonl $O/FAST3L.native $O/STD2.native $O/features-$s.csv
  echo "  $s: $(tail -1 $O/s6-features-$s.stderr) $(tail -1 $O/s6-features-$s.stdout)"
done
# 7
run s7-fit "$O/features-lizard_fairy.csv $O/features-lizard_brew.csv $O/features-none.csv" "" python3 tools/ctm_lizard.py fit --features $O/features-lizard_fairy.csv $O/features-lizard_brew.csv $O/features-none.csv --out $O/lizfit
echo "  lizfit:" >> $LOG; shas $O/lizfit/*
run s7-extend "$O/FAST3L.native $O/lizfit/fit.json" "$O/FAST4L.native" python3 tools/ctm_lizard.py extend --artifact $O/FAST3L.native --fit $O/lizfit/fit.json --out $O/FAST4L.native --fast-r --brew --fairy
run s7-manifest "$O/STD2.native $O/FAST4L.native" "$O/candidate-pathb-a20-lizard.json" python3 tools/ctm_candidate.py manifest --standard $O/STD2.native --fast $O/FAST4L.native --out $O/candidate-pathb-a20-lizard.json
python3 $CAP/hdr.py $O/STD2.native $O/FAST4L.native > $O/final-headers.txt
echo "ALL_DONE $(date -u +%FT%TZ)" | tee -a $LOG
