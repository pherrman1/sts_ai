#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- Awakened One replay (README.md) of one §727 arm-A seed.
# Every recorded Awakened One fight of the seed's arm-A game (one or two; A20 plays two act-3 bosses) is re-played
# by `one_combat fightreplay` from its recorded pre-combat state in two arms:
#   P: production (the §727 arm-A environment, learned-stop Silver); replicate 0 = identity gate (must reproduce the
#      recorded fight exactly), replicates 1-2 = fresh draws.
#   F: the same environment + STS_FIGHT_REPLAY_FLAT=40000 (flat 40k at every root, no learned stop, as §718's
#      flat40000); replicates 0-2, no identity check. Every replicate shares its battle seed with arm P (r = 0 the
#      recorded seed, r >= 1 the SEED_BASE redraws), so the arms are paired copy by copy.
# SEED_BASE 740000001. Always exits 0 (rc in the .done line).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
C=docs/experiments/evidence/ao_replay_40k_20261101
SRC=/mnt/project-files/value-chooser-ab/units
REPL=2 SEED_BASE=740000001 AO=53
[ "$(sha256sum < "$RUN/student_sel.bin" | cut -c1-16)" = cf6bf7fb7c3147dc ] || { echo "bad $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ); t0=$(date +%s)
finish() { echo "tag=$SEED rc=$1 rows=${N:-0} start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/$SEED.done"; gzip -9 -f "$OUT"/*.jsonl 2>/dev/null; exit 0; }
line=$(grep " ${SEED}\.w[0-9]*\.tar\$" "$C/source_tars.sha256") || { N=0; finish 89; }
want=${line%% *} tar=${line##* }
cp "$SRC/$tar" "$OUT/src.tar" && [ "$(sha256sum "$OUT/src.tar" | cut -d' ' -f1)" = "$want" ] || { rm -f "$OUT/src.tar"; finish 91; }
python3 -I tools/fight_replay_rows.py "$OUT/boss-$SEED.jsonl" "$OUT/src.tar" --arm A --rooms BOSS > "$OUT/rows-$SEED.log" 2>&1 || { rm -f "$OUT/src.tar"; finish 90; }
rm -f "$OUT/src.tar"
python3 -I -c "
import json, sys
rows = [l for l in open(sys.argv[1]) if l.strip() and json.loads(l)['encounter'] == int(sys.argv[3])]
open(sys.argv[2], 'w').writelines(rows)" "$OUT/boss-$SEED.jsonl" "$OUT/rows-$SEED.jsonl" "$AO" || finish 88
rm -f "$OUT/boss-$SEED.jsonl"
N=$(wc -l < "$OUT/rows-$SEED.jsonl")
[ "$N" -ge 1 ] || finish 87
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
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
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
  STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_FAST_ROOT_CAP=1024 STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$RUN/student_sel.bin")
arm() {  # arm TAG EXTRA...
  local b=$OUT/$1-$SEED; shift
  local A=("${E[@]}" "$@")
  printf '%s\n' "${A[@]}" | grep '^STS_' > "$b.env"
  env -i "${A[@]}" timeout 6h bash tools/seed_guard.sh "$RUN/one_combat" fightreplay "$N" "$OUT/rows-$SEED.jsonl" \
    "$b.jsonl" "$SEED_BASE" "$REPL" > "$b.log" 2> "$b.err"
}
arm P; rcP=$?
grep -q "Native Silver combat backend: .*learned stop gbt-0cac7cc64364; exact root budgets" "$OUT/P-$SEED.log" "$OUT/P-$SEED.err" || [ "$rcP" != 0 ] || rcP=97
[ "$rcP" = 0 ] || finish "$rcP"
arm F STS_FIGHT_REPLAY_FLAT=40000; rcF=$?
grep -q "flat=40000 identity_mismatches=0 errors=0" "$OUT/F-$SEED.log" || [ "$rcF" != 0 ] || rcF=96
finish "$rcF"
