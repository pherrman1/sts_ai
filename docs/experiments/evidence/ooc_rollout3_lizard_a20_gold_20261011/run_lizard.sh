#!/usr/bin/env bash
# §426 runner. usage: run_lizard.sh  (inputs in ~/g as in §425; checkout of #476 at 6cd03972 in $REPO)
# One replay per (gold seed, rep), REPS=1, search run seed 74004000 + 4*i + rep; 4 in parallel; outputs ~/g/out/lizard.
set -u
REPO=${REPO:-/home/user/r476}; OUT=$HOME/g/out/lizard; mkdir -p "$OUT"
cut -d, -f1 $HOME/g/targets.csv | sort -un | awk '{for(r=0;r<4;r++) print $1, r, 74004000+4*(NR-1)+r}' > "$OUT/jobs.txt"
one() {
  S=$1; R=$2; RS=$3; B=$OUT/$S.r$R
  [ -f "$B.rc" ] && return 0
  rm -f "$B.csv" "$B.jsonl"
  F=$HOME/g/force.csv; grep -qx "$S" $HOME/g/repaired_seeds.txt && F=$HOME/g/force_fixed.csv
  ( cd "$REPO"; export ARM=rollout3; source $HOME/g/env_common.sh
    m=docs/experiments/evidence/ooc_rollout3_lizard_20261010/candidate-v3-lizard.json
    export STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native \
      STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native \
      STS_OOC_MCTS_ACTIVE_LIZARD=1 STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$m \
      STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $m | cut -d' ' -f1)
    export STRATEGIC_MCTS_FORCE=$F STRATEGIC_MCTS_OUT=$B.jsonl STRATEGIC_MCTS_SEED_SHIFT=$((RS - S)) STRATEGIC_MCTS_REPS=1
    bash tools/seed_guard.sh $HOME/g/one_combat strategicgen2 1 2000 20 "$B.csv" "$S" > "$B.log" 2>&1
    echo $? > "$B.rc" )
}
export -f one; export OUT REPO
xargs -P 4 -L 1 bash -c 'one "$@"' _ < "$OUT/jobs.txt"
date -u > "$OUT/DONE"
