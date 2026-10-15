# §486 arm environments. Sourced by run_unit.sh: arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Shared part = the §457 `off` base (§422/§433 off: exact-10k Silver via the bestbench budget, V4 OOC gates at
# margin 1.0, keys off, act-3 stop, STS_OOC_MCTS=0), copied literally, plus STS_OOC_PUBLIC_FUTURES=8 as in §457.
# Every other setting is the binary's default (ADR-0030..0038 defaults ON). Ascension is the bestbench argument.
#   v4      the shared part only
#   heart1  the shared part + STS_OOC_HEART1=RUN/heart1.bin (silverbot heart1.pt, native export, sha256 in
#           heart1_weights.txt). heart1 decides every OOC screen it encodes; the rest falls back to the same chain.
arm_env_args() {
  local arm=$1 base=$2 run=$3
  case $arm in v4|heart1) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    "STS_EXECUTABLE_GIT_SHA=$(cat "$run/GITSHA")" \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    STS_OOC_MCTS=0 STS_OOC_PUBLIC_FUTURES=8 \
    "STS_OOC_DECISION_TRACE=$base.trace.jsonl"
  if [ "$arm" = heart1 ]; then
    [ -s "$run/heart1.bin" ] || { echo "missing $run/heart1.bin" >&2; return 1; }
    echo "STS_OOC_HEART1=$run/heart1.bin"
  fi
}
