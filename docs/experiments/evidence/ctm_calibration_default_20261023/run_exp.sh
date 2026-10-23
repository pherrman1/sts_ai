#!/usr/bin/env bash
# usage: run_exp.sh REPO RUN ENVFILE OUTBASE SEED [KEY=VALUE...]: one guard game with the arm environment of ENVFILE
# (written by ../ctm_calibration_20261023/run_unit.sh) without its heart1 path, git sha and calibration setting, plus
# the extra KEY=VALUE settings, on RUN/one_combat.
set -uo pipefail
REPO=$1 RUN=$2 ENVF=$3 OUT=$4 SEED=$5; shift 5
mapfile -t E < <(grep '^STS_' "$ENVF" | grep -v '^STS_OOC_HEART1=\|^STS_EXECUTABLE_GIT_SHA=\|^STS_CTM_CALIBRATION=')
E+=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
    "STS_OOC_HEART1=$RUN/student_sel.bin" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)" "$@")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$OUT.env"
cd "$REPO" || exit 2
t0=$(date +%s)
env -i "${E[@]}" timeout 7h bash tools/seed_guard.sh "$RUN/one_combat" heartoutcomegen 1 "$SEED" "$OUT.jsonl" policy > "$OUT.log" 2> "$OUT.err"
echo "rc=$? wall=$(( $(date +%s) - t0 ))" > "$OUT.done"
gzip -9 -f "$OUT.jsonl" "$OUT.ctm.jsonl" 2>/dev/null
exit 0
