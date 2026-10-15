#!/usr/bin/env bash
# Sibling-leaf capture unit (env = §486 v4 arm + capture). Resumable via .done.
# usage: run_unit.sh REPO RUN OUT TAG ASC SEED CAPTURE(0|1)
set -uo pipefail
[ -f "$OUT/$TAG-a$ASC-$SEED.done" ] && exit 0
REPO=$1 RUN=$2 OUT=$3 TAG=$4 ASC=$5 SEED=$6 CAP=$7
base=$OUT/$TAG-a$ASC-$SEED
source "$REPO/docs/experiments/evidence/heart1_ooc_ab_486_20261015/arm_env.sh"
mapfile -t E < <(arm_env_args v4 "$base" "$RUN") || exit 2
if [ "$CAP" = 1 ]; then
  E+=("STS_OOC_HEART1=$RUN/heart1.bin" "STS_OOC_SIBLING_CAPTURE=$base.sib.jsonl"
      "STS_OOC_SIBLING_EVERY=${SIB_EVERY:-4}" "STS_OOC_SIBLING_REPEATS=${SIB_REPEATS:-1}"
      "STS_OOC_SIBLING_LONG=${SIB_LONG:-0}" "STS_OOC_SIBLING_MAX_DEPTH=${SIB_DEPTH:-2}"
      "STS_OOC_SIBLING_MAX_LEAVES=${SIB_LEAVES:-256}")
fi
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 8h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 10000 1 "$ASC" "$SEED" "$base.csv" > "$base.log" 2>&1
rc=$?; times > "$base.time"
echo "tag=$TAG-a$ASC-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
