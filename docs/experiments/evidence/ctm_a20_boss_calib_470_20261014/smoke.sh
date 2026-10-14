#!/usr/bin/env bash
# §470 smoke: §457 combo_def env (automatic default CTM stack) plus STS_OOC_MCTS_A20_CTM=1, ascension 20.
set -uo pipefail
REPO=/home/user/sts_ai R=/root/calib470/smoke SEED=$1 TAG=$2; shift 2
source $REPO/docs/experiments/evidence/ooc_a20_ab_457_20261013/arm_env.sh
mapfile -t E < <(arm_env_args combo_def $R/out/$TAG $R)
E+=(STS_OOC_MCTS_A20_CTM=1)
printf '%s\n' "${E[@]}" "$@" > $R/out/$TAG.env
cd $REPO && env -i "${E[@]}" "$@" timeout 6h bash tools/seed_guard.sh /root/calib470/one_combat bestbench 10000 1 20 $SEED $R/out/$TAG.csv > $R/out/$TAG.log 2>&1
echo "rc=$?" > $R/out/$TAG.done
