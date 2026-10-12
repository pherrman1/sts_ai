#!/usr/bin/env bash
# usage: run.sh ARM SEED  (ARM = old | new); rollout3 profile at 256 sims, A0, one seed
set -uo pipefail
ARM=$1 SEED=$2 REPO=/home/user/sts_ai OUT=/tmp/claude-0/meas/out BIN=/tmp/claude-0/meas/one_combat
mkdir -p $OUT; base=$OUT/$ARM-$SEED
E=(PATH=/usr/local/bin:/usr/bin:/bin HOME=$HOME STS_EXECUTABLE_GIT_SHA=$(cat /tmp/claude-0/meas/GITSHA)
 STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
 OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
 STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1
 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3
 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 STS_OOC_DECISION_TRACE=$base.trace.jsonl
 STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=256 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native
 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_CPUCT=1.5
 STS_OOC_MCTS_WIDEN_K=2 STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_MAX_DEPTH=32
 STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 STS_OOC_MCTS_TRACE=$base.mcts.csv)
# old = the #418 stack the automatic default used before this change, selected explicitly
[ "$ARM" = old ] && E+=(STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2.native
  STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native STS_OOC_MCTS_ACTIVE_LIZARD=1)
cd $REPO
s=$(date +%s)
env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh $BIN bestbench 10000 1 0 $SEED $base.csv > $base.log 2>&1
echo "arm=$ARM seed=$SEED rc=$? sec=$(( $(date +%s)-s ))" > $base.done
