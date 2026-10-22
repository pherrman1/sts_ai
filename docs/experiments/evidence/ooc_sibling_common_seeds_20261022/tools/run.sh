#!/usr/bin/env bash
# usage: SP=<dir with student_sel.bin> run.sh BIN OUTDIR TAG SEED GITSHA [EXTRA_ENV...]
# The #806 quick smoke (value_leaf_blend_20261022/tools/smoke_run.sh: §621 arm A, 256 simulations, learned OOC stop
# off) plus sibling capture every 4th searched root: 32 rollout3 repeats per root child, at most 64 children.
set -u
BIN=$1 OUT=$2 TAG=$3 SEED=$4 SHA=$5; shift 5
REPO=${REPO:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}
bash "$REPO/docs/experiments/evidence/value_leaf_blend_20261022/tools/smoke_run.sh" "$BIN" "$OUT" "$TAG" "$SEED" \
  STS_EXECUTABLE_GIT_SHA=$SHA STS_OOC_MCTS_SIMS=256 STS_OOC_MCTS_LEARNED_STOP=0 \
  STS_OOC_SIBLING_CAPTURE=$OUT/$TAG.sib.jsonl STS_OOC_SIBLING_EVERY=4 STS_OOC_SIBLING_REPEATS=32 STS_OOC_SIBLING_LONG=0 \
  STS_OOC_SIBLING_MAX_DEPTH=1 STS_OOC_SIBLING_MAX_LEAVES=64 "$@"
