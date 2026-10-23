#!/bin/bash
# score_ft.sh CKPT_DIR OUT_DIR [act4off]: export the fine-tune and score the five row sets through the pathb-a20 stack
set -euo pipefail
cd /home/user/sts_ai
B=selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
STD=selfplay/models/combat_transition_near_full_escape_pathb_a20.native
SHA=ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b
BIN=build/linux-gcc-release-x86-64-v3/one_combat
C=$1; O=$2; mkdir -p $O
[ -f $C/ft.native ] || python3 tools/ctm_finetune.py export --base $B --base-sha $SHA --checkpoint $C/finetune.pt --out $C/ft.native --manifest-out $C/manifest.json > $C/export.json
export STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$(realpath $C/manifest.json) STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=$(sha256sum $C/manifest.json | cut -d' ' -f1) STS_ACTIVE_POWER_FEATURES=1
export STS_CTM_CALIBRATION=0   # raw net: never a calibration table (pinned, so a future default cannot change these scores)
[ "${3:-}" = act4off ] && export STS_CTM_ACT4_SURVIVAL_MODEL=0
for s in ${SETS:-A M S MS LC}; do $BIN ctmscorerows /home/user/work/rows/$s.jsonl $O/$s.csv $C/ft.native $STD 1 2> $O/$s.err > /dev/null & done; wait
grep -h "rows=" $O/*.err
