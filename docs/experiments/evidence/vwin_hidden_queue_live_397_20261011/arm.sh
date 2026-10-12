#!/usr/bin/env bash
# usage: arm.sh ARM LO N OUTBASE   (ARM = legacy | public8). Sole difference: STS_OOC_PUBLIC_FUTURES.
set -uo pipefail
ARM=$1 LO=$2 N=$3 BASE=$4
case $ARM in legacy) PF=0;; public8) PF=8;; *) echo bad arm; exit 2;; esac
cd /home/user/sts_ai
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=$HOME STS_EXECUTABLE_GIT_SHA=491bc21bb2b2192e3547bdd2b4a1360add8489d7 \
  STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
  STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
  STS_OOC_MCTS=0 STS_OOC_PUBLIC_FUTURES=$PF STS_OOC_DECISION_TRACE=$BASE.trace.jsonl \
  timeout 6h bash tools/seed_guard.sh /tmp/claude-0/vw397/run/one_combat bestbench 10000 "$N" 0 "$LO" "$BASE.csv" > "$BASE.log" 2>&1
echo "arm=$ARM lo=$LO n=$N rc=$?" > "$BASE.done"
