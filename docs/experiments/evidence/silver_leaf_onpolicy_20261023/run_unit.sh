#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT VARIANT FIRST_SEED COUNT -- COUNT A20 self-play runs of `one_combat silverazgen`
# (seeds FIRST_SEED.., variant natural): whole runs as ../silver_leaf_a20_prod_20261022 (production A20 settings,
# student_sel argmax out of combat through runFullRunOOC's chain, flat 10,000-simulation production Silver), except
# that the fights play the §664 searched-value head (RUN/q_e2e_head.txt on RUN/q_e2e_trunk.txt, blend 0.5, no turn
# penalty, no win-now cap) and STS_AZGEN_LABEL_SEARCH=1 searches every root again with production Silver for the
# label (record_env.sh). Every root row's `edges` are that label search's, `playEdges` the played search's; every
# fight row carries the head's own end score `score`. Always exits 0 (rc is in .done; rc=97 when the run's manifest
# does not say it played the production out-of-combat chain, production combat with boss prior playouts, the frozen
# head and trunk at blend 0.5 without turn penalty or cap, and a label search at every root).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 VARIANT=$4 FIRST=$5 COUNT=$6
case $VARIANT in natural) ;; *) echo "bad variant $VARIANT" >&2; exit 2 ;; esac
[[ "$FIRST" =~ ^[0-9]+$ && "$COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "bad seeds $FIRST $COUNT" >&2; exit 2; }
for f in student_sel.bin q_e2e_head.txt q_e2e_trunk.txt; do
  [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }
done
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CODE=$(awk '$1=="code_commit"{print $2}' "$D/campaign.manifest")
HEAD_SHA=$(awk '$1=="input" && $2=="q_e2e_head.txt"{print $4}' "$D/campaign.manifest")
TRUNK_SHA=$(awk '$1=="input" && $2=="q_e2e_trunk.txt"{print $4}' "$D/campaign.manifest")
source "$D/record_env.sh"
mkdir -p "$OUT"; base=$OUT/$VARIANT-$FIRST
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" "${SL_ENV[@]}" "STS_OOC_HEART1=$RUN/student_sel.bin" \
  "STS_SILVER_LEAF_HEAD=$RUN/q_e2e_head.txt" "STS_SILVER_LEAF_HEAD_TRUNK=$RUN/q_e2e_trunk.txt" \
  "STS_EXECUTABLE_GIT_SHA=$CODE" timeout 4h bash tools/seed_guard.sh "$RUN/one_combat" silverazgen "$COUNT" 10000 20 \
  "$base" "$FIRST" "$VARIANT" 8 1 > "$base.log" 2>&1 || rc=$?
[ -s "$base.jsonl" ] && gzip -f "$base.jsonl"
[ "$rc" = 0 ] && { python3 - "$base.manifest.json" "$HEAD_SHA" "$TRUNK_SHA" <<'PY' || rc=97
import json, sys
m = json.load(open(sys.argv[1]))
leaf = m["silverLeaf"]
head = leaf["leaf_head"]
assert m["oocPlay"] == "production_chain" and m["combat"] == "production" and leaf["prior_playout_rooms"] == "boss"
assert head["sha256"] == sys.argv[2] and head["trunk"]["sha256"] == sys.argv[3]
assert head["blend"] == 0.5 and head["turn_penalty"] == 0 and not head.get("win_cap")
assert m["labelSearch"]["labelRoots"] == m["integrity"]["roots"] > 0
PY
}
echo "tag=$VARIANT-$FIRST rc=$rc roots=$(grep -o 'roots=[0-9]*' "$base.log" | tail -1) start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
