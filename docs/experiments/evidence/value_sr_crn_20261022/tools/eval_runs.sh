#!/bin/bash
# usage: V=<work dir> DATA=<clone of claude/az-gen2-data> REPO=<sts_ai checkout> CRN=<crn_analyze.py rows output> \
#        eval_runs.sh TAG NAME...
# Cloud evaluation of the SR-CRN heads pushed to gen2/value-sr-crn/weights/ on the data branch (value-head research,
# 2026-10-22). V is #812's evaluation directory (one_combat sha256 193b0000…, s494/, r2/, prices/, work3/ with SR_w1's
# round-2 outputs, and SR_w1.bin). CRN holds the common-seed capture's rows and records (§644); head values are cached
# there per weights stem. Per head: the prices gate against M0.3 and SR_w1; crn_eval.py on the common-seed VALIDATION
# and TRAIN holdout, with SR_w1 as the control; then value_leaf_check.py check and #812's sr_eval.py on round 2, again
# with SR_w1 as the control. Outputs land in the directory the script is called from. one_combat reads model files
# relative to the repository, so the scoring steps run from REPO.
set -eu
T=$(cd "$(dirname "$0")" && pwd); OUT=$PWD; P=$V/prices; TAG=$1; shift
cd "$REPO"
nets=(); crn=("SR_w1=$V/SR_w1.bin"); r2=("SR_w1=$V/work3")
for n in "$@"; do
  cp "$DATA/gen2/value-sr-crn/weights/$n/student.bin" "$V/$n.bin"
  echo "$n bin $(sha256sum "$V/$n.bin" | cut -c1-16)"
  nets+=("$n=$V/$n.bin"); crn+=("$n=$V/$n.bin"); r2+=("$n=$V/work3")
  "$V/one_combat" heart1score "$V/$n.bin" "$P/records.jsonl" "$P/$n.scores.jsonl" > /dev/null 2>&1
  python3 "$P/prices.py" analyze "$P/meta.json" "$P/$n.scores.jsonl" "$P/$n-prices.json" > /dev/null
done
(cd "$P" && python3 gate.py M0.3 SR_w1 "$@") | tee "$OUT/prices_$TAG.txt"
STS_REPO=$REPO python3 "$T/crn_eval.py" "$V/one_combat" "$CRN" "$OUT/crn_eval_$TAG.json" "${crn[@]}" \
  | tee "$OUT/crn_eval_$TAG.txt"
python3 tools/heart1/value_leaf_check.py check "$V/one_combat" "$V/sr_check_$TAG.json" "$V/work3" "$V/s494" "$V/r2" \
  "${nets[@]}" > /dev/null
python3 docs/experiments/evidence/value_sibling_rank_20261022/tools/sr_eval.py "$V/r2" "$V/s494" \
  "$OUT/sr_eval_$TAG.json" "${r2[@]}" | tee "$OUT/sr_eval_$TAG.txt"
