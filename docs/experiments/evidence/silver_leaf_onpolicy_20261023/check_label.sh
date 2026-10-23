#!/usr/bin/env bash
# The generator checks of the README: 2 A20 natural runs (seeds 111399990-991, production chain and combat, as
# record_env.sh) at SIMS simulations in three modes: prod (no head), head (the q_e2e head, no label search) and label
# (head + STS_AZGEN_LABEL_SEARCH=1). BASE is a binary of main without this change, NEW one with it; A/B = prod/head
# with each binary, C = label with NEW; then compare_label.py and the feature extractor's counts on each NEW output.
# usage (repo root): check_label.sh BASE NEW OUT [SIMS]
set -uo pipefail
BASE=$1 NEW=$2 OUT=$3 SIMS=${4:-1000}
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); R=$(pwd)
L=/mnt/project-files/exact-combat-research/leaf-value/label-data-20261023/nets
SEL=/mnt/project-files/az-gen3-explore/student_sel.bin
CODE=$(git -C "$R" rev-parse HEAD)
source "$D/record_env.sh"
mkdir -p "$OUT"
one() {   # BIN TAG MODE
  local env=() e
  for e in "${SL_ENV[@]}"; do
    case $e in STS_SILVER_LEAF_HEAD_*) [ "$3" = prod ] && continue ;; esac
    case $e in STS_AZGEN_LABEL_SEARCH=*) [ "$3" != label ] && continue ;; esac
    env+=("$e")
  done
  [ "$3" != prod ] && env+=("STS_SILVER_LEAF_HEAD=$L/q_e2e_head.txt" "STS_SILVER_LEAF_HEAD_TRUNK=$L/q_e2e_trunk.txt")
  local t0=$(date +%s)
  env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" "${env[@]}" "STS_OOC_HEART1=$SEL" "STS_EXECUTABLE_GIT_SHA=$CODE" \
    "$1" silverazgen 2 "$SIMS" 20 "$OUT/$2" 111399990 natural 8 1 > "$OUT/$2.log" 2>&1
  echo "$2 rc=$? wall=$(( $(date +%s) - t0 ))s" >> "$OUT/$2.log"
}
one "$BASE" A_base prod & one "$NEW" A_new prod & one "$BASE" B_base head & one "$NEW" B_new head & wait
one "$NEW" C_new label
python3 "$D/compare_label.py" "$OUT"
for t in A_new B_new C_new; do
  rm -f "$OUT/x_$t".*
  "$NEW" silversynthfeatures "$OUT/x_$t" < "$OUT/$t.jsonl" > /dev/null 2>&1
  echo "extractor $t: $(tr -d ' \n' < "$OUT/x_$t.summary.json" | grep -o '"counts":{[^}]*}')"
  rm -f "$OUT/x_$t".{nnz,idx,val,meta.jsonl}
done
grep -h "wall=" "$OUT"/*.log
