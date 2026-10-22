#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT VARIANT FIRST_SEED COUNT -- COUNT A20 self-play runs of `one_combat silverazgen`
# (seeds FIRST_SEED.., variant natural or perturbed): flat 10,000-simulation Silver with the g7f_E prior as tree prior
# (K = 8, no root bonus), production A20 settings otherwise (record_env.sh), student_sel argmax out of combat. Every
# searched root is one row (state, edges with visits and Q); every fight row carries Silver's own end score `score`.
# Always exits 0 (rc is in .done).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 VARIANT=$4 FIRST=$5 COUNT=$6
case $VARIANT in natural|perturbed) ;; *) echo "bad variant $VARIANT" >&2; exit 2 ;; esac
[[ "$FIRST" =~ ^[0-9]+$ && "$COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "bad seeds $FIRST $COUNT" >&2; exit 2; }
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CODE=$(awk '$1=="code_commit"{print $2}' "$D/campaign.manifest")
source "$D/record_env.sh"
mkdir -p "$OUT"; base=$OUT/$VARIANT-$FIRST
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" "${SL_ENV[@]}" "STS_OOC_HEART1=$RUN/student_sel.bin" \
  "STS_EXECUTABLE_GIT_SHA=$CODE" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" silverazgen "$COUNT" 10000 20 \
  "$base" "$FIRST" "$VARIANT" 8 0 > "$base.log" 2>&1 || rc=$?
[ -s "$base.jsonl" ] && gzip -f "$base.jsonl"
echo "tag=$VARIANT-$FIRST rc=$rc roots=$(grep -o 'roots=[0-9]*' "$base.log" | tail -1) start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
