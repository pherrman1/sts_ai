# Ritual refit A/B arm environments. arm_env_args ARM BASE RUN -> KEY=VALUE lines for env -i.
# Base: the §488 `studentc` arm literally (§433 `combo`: exact-10k Silver via the bestbench budget, V4 OOC gates at
# margin 1.0, keys off, act-3 stop; live OOC MCTS 4096 sims, WIDEN_K=4, WIDEN_ALPHA=0.75, 3 leaf combats, native leaf,
# STS_OOC_PUBLIC_FUTURES=8, chain rollouts) with Arm C (student C, eff2f74f…) as the tree prior, at ascension 0.
# The arms differ only in the A0 CTM pair (both with active Lizard, as the automatic A0 stack and the live mod use):
#   control  deployed pathb-r2 pair (c6d56bbc… fast, b9188de0… Brew fallback); Writhing + Ritual Dagger refused
#   ritual   pathb-r2-ritual-refit pair (3bbff6b6… / 2f0f5d97…, writhingRitual) via its research-candidate manifest
arm_env_args() {
  local arm=$1 base=$2 run=$3
  case $arm in control|ritual) ;; *) echo "unknown arm $arm" >&2; return 1 ;; esac
  [ -s "$run/studentc.bin" ] || { echo "missing $run/studentc.bin" >&2; return 1; }
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    "STS_EXECUTABLE_GIT_SHA=$(cat "$run/GITSHA")" \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    "STS_OOC_DECISION_TRACE=$base.trace.jsonl" \
    STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=4096 STS_OOC_MCTS_LEAF_COMBATS=3 STS_OOC_MCTS_LEAF_VALUE=native \
    STS_OOC_MCTS_TEMPERATURE=1 STS_OOC_MCTS_CPUCT=1.5 \
    STS_OOC_MCTS_WIDEN_K=4 STS_OOC_MCTS_WIDEN_ALPHA=0.75 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_EARLY_STOP=1 "STS_OOC_MCTS_TRACE=$base.mcts.csv" \
    STS_OOC_PUBLIC_FUTURES=8 STS_OOC_MCTS_LEAF_POLICY=v4 \
    "STS_OOC_HEART1=$run/studentc.bin" STS_OOC_MCTS_PRIOR=heart1 STS_OOC_MCTS_ACTIVE_LIZARD=1
  if [ "$arm" = control ]; then
    printf '%s\n' STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native \
      STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native
  else
    local m=docs/experiments/evidence/ctm_ritual_refit_20261017/candidate-manifest.json
    printf '%s\n' STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard_ritual_refit.native \
      STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2_ritual_refit.native \
      "STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$m" "STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(cat "$run/MANIFEST_SHA256")"
  fi
}
