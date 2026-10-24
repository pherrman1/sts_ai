#!/usr/bin/env bash
# usage: score.sh BIN ROWS OUT FAST [KEY=VALUE...] -- `one_combat ctmscorerows` of ROWS/{A,LC,gA,gC}.jsonl through the
# A20 stack (FAST + the A20 standard artifact, Lizard correction on) with only the given CTM settings, from the repo.
#   A, LC   §670's stage-3 A/B arm A and held-out stage 1-2 rows (../ctm_calibration_20261023/offline/extract.sh)
#   gA, gC  the guard's rows: the concatenated *.ctm.jsonl.gz of each arm in path order (../ctm_calibration_20261023/RESULT.md)
# SETS="LC" scores a subset.
set -euo pipefail
BIN=$1 ROWS=$2 OUT=$3 FAST=$4; shift 4
STD=selfplay/models/combat_transition_near_full_escape_pathb_a20.native
mkdir -p "$OUT"
for k in ${SETS:-A LC gA gC}; do
  env -u STS_CTM_CALIBRATION -u STS_CTM_A20_HP_FINETUNE -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST \
      -u STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256 -u STS_CTM_ACT4_SURVIVAL_MODEL "$@" \
      "$BIN" ctmscorerows "$ROWS/$k.jsonl" "$OUT/$k.csv" "$FAST" "$STD" 1 > /dev/null 2> "$OUT/$k.err" &
done
wait
(cd "$OUT" && sha256sum ./*.csv)
