#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT ARM SEED -- one guarded one-seed A20 bestbench full run (2 h timeout: rc 124);
# always exits 0 (rc is in the .done line; the analyzer drops seeds with any rc != 0 arm, PREREG.md).
# All arms (PREREG.md): plain A20 full runs, OOC decisions by student_sel policyStep (no OOC MCTS, no V4 net),
# Silver with the gen-7f MLP as rollout root table AND as root prior (weight 400) / tree prior (K=8),
# STS_ACTIVE_POWER_FEATURES=1.
#   F10  flat exact 10k Silver     F25  flat exact 2.5k Silver     L  learned stopping (ADR-0026, checkpoints to 10k)
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 SEED=$5
case $ARM in F10) SIMS=10000 LS=0 ;; F25) SIMS=2500 LS=0 ;; L) SIMS=10000 LS=1 ;; *) echo "unknown arm $ARM" >&2; exit 2 ;; esac
[ -s "$RUN/student_sel.bin" ] || { echo "missing $RUN/student_sel.bin" >&2; exit 2; }
PRIOR=models/combat_policy_mlp_g7f_E.txt
mkdir -p "$OUT"; base=$OUT/$ARM-$SEED
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 "STS_SILVER_LEARNED_STOP=$LS"
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 STS_ACTIVE_POWER_FEATURES=1
  "STS_SILVER_ROLLOUT_ROOT_TABLE=$PRIOR" "STS_SILVER_ROOT_PRIOR=$PRIOR"
  STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  "STS_OOC_HEART1=$RUN/student_sel.bin" STS_OOC_CPU_PROFILE=1 "STS_OOC_DECISION_TRACE=$base.ooc.jsonl")
printf '%s\n' "${E[@]}" | grep '^STS_' > "$base.env"
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" bestbench "$SIMS" 1 20 "$SEED" "$base.csv" > "$base.log" 2> "$base.err"
rc=$?
# The table must have loaded; a run without it is not this arm.
[ "$rc" = 0 ] && ! grep -q "rollout root table model loaded: $PRIOR" "$base.err" "$base.log" && rc=97
echo "tag=$ARM-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
