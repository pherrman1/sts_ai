#!/bin/bash
# Shield and Spear (32 recorded A20 Act-4 entry states, act4replay, 4 copies each = seeds 111149768-895): production
# Silver at flat 10k with the g7f_E root/tree prior and greedy root-table playouts (default since ADR-0056) vs the same
# with prior playouts in elite rooms (STS_SILVER_PRIOR_PLAYOUT_ELITE=1, ADR-0050's rooms). Paired by seed.
S=/tmp/claude-0/-home-user-sts-ai/cbf6dcc2-01d6-5260-ac1b-f327e87f9ba1/scratchpad
B=$S/bin/oc2/one_combat
cd /home/user/sts_ai
until grep -q 'phase2 done' $S/pp/run_all.log; do sleep 20; done
echo "start $(date -u +%T)"
export STS_FAIR=1 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0 \
  STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_LEARNED_STOP=0 STS_COLLECT_KEYS=1 OMP_NUM_THREADS=4 \
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8
bash tools/seed_guard.sh $B act4replay 32 $S/ss/ss32.jsonl $S/ss/ss_greedy 111149768 10000 4 > $S/ss/ss_greedy.log 2>&1
echo "greedy done $(date -u +%T)"
STS_SILVER_PRIOR_PLAYOUT_ELITE=1 bash tools/seed_guard.sh $B act4replay 32 $S/ss/ss32.jsonl $S/ss/ss_prior 111149768 10000 4 > $S/ss/ss_prior.log 2>&1
echo "prior done $(date -u +%T)"
