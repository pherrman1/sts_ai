#!/usr/bin/env bash
set -euo pipefail
base=/tmp/ooc-policy-prefix-candidate-41c0f5a/one_combat
both=/home/philippherrmann/.codex/worktrees/dd01/sts_lightspeed/build/linux-gcc-release/one_combat
for spec in base1:base both1:both both2:both base2:base; do
  name=${spec%%:*}
  which=${spec##*:}
  if [[ $which == base ]]; then exe=$base; else exe=$both; fi
  out=/tmp/ooc-prior-singleton-verified-exact-41c0f5a/$name
  env OMP_NUM_THREADS=1 STS_EXECUTABLE_GIT_SHA=41c0f5af5711c452b6e133e6dc66c7756f50874c \
      STS_OOC_MCTS=1 STS_OOC_CPU_PROFILE=1 STS_STOP_AFTER_ACT=3 \
      STS_COLLECT_KEYS=0 \
      STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_EVENT=1 \
      STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1 \
      STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1 \
      STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
      STS_OOC_MCTS_COMBAT_MODEL=/tmp/ooc-deepset-stack-provenance-review.native \
      STS_OOC_MCTS_TRACE="$out.mcts.csv" \
      STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 \
      STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 \
      STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_REUSE_CAP=32768 \
      STS_NATIVE_OOC=1 \
      STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_PRIOR=policy \
      STS_OOC_MCTS_LEAF_POLICY=uniform STS_OOC_MCTS_LEAF_VALUE=native \
      STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_TEMPERATURE=1 \
      STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_WIDEN_K=2 \
      STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_MAX_DEPTH=32 \
      STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 \
      /usr/bin/time -v -o "$out.time" bash tools/seed_guard.sh "$exe" bestbench 10000 1 0 12002032 "$out.csv" >"$out.stdout" 2>"$out.stderr"
done
