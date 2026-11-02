#!/usr/bin/env bash
# Part B of PREREG.md: replay §727 arm A (value_chooser_ab_20261031/run_unit.sh, arm A environment verbatim, no
# chooser) on seeds 111312000-111312031 (used; replays) and write A-<seed>.jsonl.gz for compare.py.
#   run_b.sh REPO BIN OUT [LANES]     (SEEDS="..." overrides the seed list, e.g. to finish a killed game)
# REPO: checkout whose model files the game reads (B1: a detached worktree at 8f5b17d6; B2: main e55f482).
# BIN:  one_combat (B1: bin-cache one_combat-d39c2b98...; B2: fresh linux-gcc-release-x86-64-v3 build at e55f482).
# OUT:  fresh output dir; student_sel.bin (cf6bf7fb...) is copied there from the share.
set -uo pipefail
REPO=$(cd "$1" && pwd) BIN=$(readlink -f "$2") OUT=$3 LANES=${4:-4}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" || exit 2
[ -z "$(ls -A "$OUT")" ] || { echo "OUT not empty" >&2; exit 2; }
cp /mnt/project-files/az-gen3-explore/student_sel.bin "$OUT/student_sel.bin"
[ "$(sha256sum < "$OUT/student_sel.bin" | cut -c1-16)" = cf6bf7fb7c3147dc ] || { echo "bad student_sel.bin" >&2; exit 2; }
sha256sum "$BIN" > "$OUT/binary.sha256"
git -C "$REPO" rev-parse HEAD > "$OUT/repo.sha"
one() {
  local SEED=$1 b=$OUT/A-$1
  local E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
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
  STS_HEART_OUTCOME_CTM_ROWS=1 "STS_OOC_HEART1=$OUT/student_sel.bin")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  local t0=$(date +%s)
  (cd "$REPO" && env -i "${E[@]}" timeout 7h bash "$HERE/../../../../tools/seed_guard.sh" "$BIN" heartoutcomegen 1 "$SEED" \
     "$b.jsonl" policy > "$b.log" 2> "$b.err")
  local rc=$?
  echo "A-$SEED rc=$rc wall=$(( $(date +%s)-t0 ))" > "$b.done"
  gzip -9 -f "$b.jsonl" "$b.ctm.jsonl" 2>/dev/null
}
export -f one; export OUT REPO BIN HERE HOME
printf '%s\n' ${SEEDS:-$(seq 111312000 111312031)} | xargs -P "$LANES" -I{} bash -c 'one {}'
echo "run_b done $(ls "$OUT"/*.done | wc -l) games"
