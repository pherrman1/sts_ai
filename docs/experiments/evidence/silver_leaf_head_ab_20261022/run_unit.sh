#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT S SEED -- one guarded A20 ctmsilvergen source (armset leafhead, R = 2):
# base10000, base12000 and base15000 (production Silver) vs head10000 (leaves: 50/50 blend of the silver-leaf-a20 value
# head, capped at the leaf's win-now value and then lowered 1 point per turn beyond the root, and the playout), the
# §541 harness as ../silver_maxbackup_ab_20261022.
# No OOC MCTS, so no imagined fights; the armset also refuses the imagined-fight Silver options. Always exits 0 (rc is
# in .done).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 KIND=$4 SEED=$5
[ "$KIND" = S ] || { echo "unknown unit kind $KIND" >&2; exit 2; }
for f in studentc.bin a20.txt; do [ -s "$RUN/$f" ] || { echo "missing $RUN/$f" >&2; exit 2; }; done
PRIOR=$REPO/models/combat_policy_mlp_g7f_E.txt
mkdir -p "$OUT"; base=$OUT/S-$SEED
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated
  STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0
  "STS_SILVER_ROOT_PRIOR=$PRIOR" STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1
  STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_REST_WIN=0
  STS_COLLECT_KEYS=0 STS_STOP_AFTER_ACT=3 "STS_OOC_HEART1=$RUN/studentc.bin"
  STS_CTMSILVER_ARMSET=leafhead STS_CTMSILVER_SWEEP_SIMS=10000,12000,15000 STS_CTMSILVER_HEAD_SIMS=10000
  STS_CTMSILVER_HALLWAY_EVERY=3 "STS_CTMSILVER_LEAF_HEAD=$RUN/a20.txt" "STS_CTMSILVER_LEAF_HEAD_TRUNK=$PRIOR"
  STS_CTMSILVER_LEAF_HEAD_BLEND=0.5 STS_CTMSILVER_LEAF_HEAD_TURN_PENALTY=1 STS_CTMSILVER_LEAF_HEAD_WIN_CAP=1)
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
env -i "${E[@]}" python3 tools/silver_synth_teacher.py "$(git rev-parse HEAD)" "$RUN/one_combat" "$base.teacher.json" \
  > "$base.teacher.log" 2>&1 || rc=$?
[ $rc = 0 ] && { env -i "${E[@]}" "$RUN/one_combat" vwinrefreshpolicyspec "$base.policy.json" > /dev/null 2>> "$base.teacher.log" || rc=$?; }
[ $rc = 0 ] && { python3 - "$base.teacher.json" "$base.policy.json" <<'PY' || rc=$?
import json, sys
t = json.load(open(sys.argv[1])); t["ooc_policy"] = json.load(open(sys.argv[2]))
json.dump(t, open(sys.argv[1], "w"), indent=2)
PY
}
[ $rc = 0 ] && { env -i "${E[@]}" timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" ctmsilvergen 1 20 "$base" "$SEED" \
  "$base.teacher.json" 2 > "$base.log" 2>&1 || rc=$?; }
echo "tag=S-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
