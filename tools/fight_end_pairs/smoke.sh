#!/usr/bin/env bash
# usage: tools/fight_end_pairs/smoke.sh BIN STUDENT_SEL OUT_DIR SEED [OPTIONS] [VARIANTS]
# One fightendpairgen source seed in the §739 cheap-combat environment: flat Silver 1,000 sims per decision
# (learned stop and Act 4 strong off), student_sel out of combat (STS_OOC_MCTS=0, ooc=heart1 lets the student
# take every OOC step it encodes inside the continuations), flexible keys. Only for already-used smoke seeds;
# anything larger needs Philipp's go and a frozen PREREG. Writes OUT_DIR/fe-SEED.{jsonl,manifest.json,env,log,err}.
set -uo pipefail
BIN=$1 STUDENT=$2 OUT=$3 SEED=$4 OPTIONS=${5:-n=2,ooc=heart1} VARIANTS=${6:-default}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$OUT"
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=0 "STS_OOC_HEART1=$STUDENT")
b=$OUT/fe-$SEED
printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
cd "$REPO" || exit 2
env -i "${E[@]}" bash tools/seed_guard.sh "$BIN" fightendpairgen 1 "$SEED" 1000 20 "$b.jsonl" "$OPTIONS" "$VARIANTS" \
  > "$b.log" 2> "$b.err"
echo "rc=$?" >> "$b.log"
