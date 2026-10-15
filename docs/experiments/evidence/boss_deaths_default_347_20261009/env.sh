# Default stack for the #347 boss-death replay (PLAN.md): the ADR-0026 live
# profile (V4 gate stack, learned-stop Silver) with OOC MCTS off and the Act-3
# horizon explicit. Everything else is the executable default.
source docs/experiments/evidence/silver_learned_stop/live_env.sh
export STS_SILVER_LEARNED_STOP=1 STS_SILVER_ADAPTIVE=0 STS_OOC_MCTS=0 STS_STOP_AFTER_ACT=3
