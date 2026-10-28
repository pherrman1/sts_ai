#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- post-hoc fight replay of one §676 guard seed (both arms A and C);
# always exits 0 (rc in the .done line). PREREG.md has the config and provenance.
# Input: the seed's §676 unit tar (read from the share, hash-checked against source_tars.sha256). Every recorded
# non-event fight of both arms is re-played by `one_combat fightreplay`: replicate 0 with the recorded seed must
# reproduce the fight exactly (identity gate; any mismatch -> rc 1), replicates 1-4 are fresh draws (SEED_BASE
# 676000001). Combat config = the §676 units' frozen env (both arms share it: the arms differ only in the CTM, which
# real combat never reads) plus STS_SILVER_ACT4_STRONG=0, because §676 ran before #852.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
C=docs/experiments/evidence/aivat_replay_676_20261026
SRC=/mnt/project-files/ctm-calibration-ab/units
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"
cd "$REPO" || exit 2
line=$(grep " ${SEED}\.w[0-9]*\.tar\$" "$C/source_tars.sha256") || { echo "no source tar for $SEED" > "$OUT/$SEED.done"; exit 0; }
want=${line%% *} tar=${line##* }
start=$(date -u +%FT%TZ); t0=$(date +%s)
cp "$SRC/$tar" "$OUT/src.tar" && [ "$(sha256sum "$OUT/src.tar" | cut -d' ' -f1)" = "$want" ] || {
  echo "tag=$SEED rc=91 source tar missing or hash mismatch" > "$OUT/$SEED.done"; rm -f "$OUT/src.tar"; exit 0; }
python3 -I tools/fight_replay_rows.py "$OUT/rows-$SEED.jsonl" "$OUT/src.tar" > "$OUT/rows-$SEED.log" 2>&1 || {
  echo "tag=$SEED rc=90 row build failed" > "$OUT/$SEED.done"; rm -f "$OUT/src.tar"; exit 0; }
rm -f "$OUT/src.tar"
N=$(wc -l < "$OUT/rows-$SEED.jsonl")
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0 STS_SILVER_ACT4_STRONG=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=1 STS_OOC_MCTS_PRIOR=heart1full STS_OOC_MCTS_LEAF_POLICY=heart1
  STS_OOC_MCTS_TARGET_PRIOR=1 STS_OOC_MCTS_LEAF_SELECTS=heart1 STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=500
  STS_OOC_MCTS_LEAF_VALUE=native STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_SIMS=4096
  STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1
  STS_OOC_MCTS_MAX_DEPTH=32 STS_OOC_MCTS_TREE_RULES=1 STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75
  STS_OOC_MCTS_PRUNE_UNSUPPORTED=1 STS_OOC_MCTS_GAP_STOP=0
  STS_OOC_MCTS_LEARNED_STOP=models/candidates/ooc_learned_stop_trees.txt:0.99
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25 STS_OOC_MCTS_FAST_ROOT_CAP=1024
  STS_HEART_OUTCOME_CTM_ROWS=1 STS_CTM_CALIBRATION=0 "STS_OOC_HEART1=$RUN/student_sel.bin")
b=$OUT/replay-$SEED
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
env -i "${E[@]}" timeout 5h bash tools/seed_guard.sh "$RUN/one_combat" fightreplay "$N" "$OUT/rows-$SEED.jsonl" \
  "$b.jsonl" 676000001 4 > "$b.log" 2> "$b.err"
rc=$?
grep -q "Native Silver combat backend: .*learned stop gbt-0cac7cc64364; exact root budgets" "$b.log" "$b.err" || [ "$rc" != 0 ] || rc=97
echo "tag=$SEED rc=$rc rows=$N start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/$SEED.done"
gzip -9 -f "$OUT"/*.jsonl 2>/dev/null
exit 0
