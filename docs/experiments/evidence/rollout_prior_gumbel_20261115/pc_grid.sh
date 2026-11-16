#!/usr/bin/env bash
# Stage-1 training grid on the PC GPU (PREREG.md). Runs V and CQP finished in the cloud (4 CPU threads, same code).
# usage: pc_grid.sh REPO PACK.npz RUNS_DIR PHASE    PHASE = a (targets) | b (aux heads, boss fine-tune, seed 1)
# Phase b reads phase a's train.json files (and the cloud's V / CQP, copied into RUNS_DIR) and picks the target by
# the PREREG rule: lowest playout-room q_regret_backed; within 0.01 the lower q_regret_mean.
set -euo pipefail
REPO=$1 PACK=$2 RUNS=$3 PHASE=$4
PY=${PY:-python3 -P}
T="$REPO/tools/rollout_prior/train.py"
mkdir -p "$RUNS"
fit() {  # name args...
  local name=$1; shift
  [ -f "$RUNS/$name/train.json" ] && { echo "kept $name"; return; }
  $PY "$T" fit "$PACK" "$RUNS/$name" --device cuda --threads 8 "$@" > "$RUNS/$name.log" 2>&1
  grep RESULT "$RUNS/$name.log" | cut -c1-400
}
if [ "$PHASE" = a ]; then
  fit CQ30 --target cq:30 --q-source backed
  fit CQ10 --target cq:10 --q-source backed
  fit CQ30m --target cq:30 --q-source mean
  exit 0
fi
read -r BEST TGT QS < <($PY - "$RUNS" <<'EOF'
import json, sys, os
runs = {"V": ("visits", "backed"), "CQP": ("cq:paper", "backed"), "CQ30": ("cq:30", "backed"),
        "CQ10": ("cq:10", "backed"), "CQ30m": ("cq:30", "mean")}
res = {}
for k, spec in runs.items():
    p = os.path.join(sys.argv[1], k, "train.json")
    if os.path.exists(p):
        f = json.load(open(p))["val_final"]["playout"]
        res[k] = (f["q_regret_backed"], f["q_regret_mean"], spec)
best = min(res, key=lambda k: res[k][0])
close = [k for k in res if res[k][0] - res[best][0] <= 0.01]
best = min(close, key=lambda k: res[k][1])
print(best, *res[best][2])
EOF
)
echo "phase b target: $BEST ($TGT, $QS)"
fit X-Q --target "$TGT" --q-source "$QS" --aux-q 1
fit X-SH --target "$TGT" --q-source "$QS" --aux-sh 0.5
fit X-QSH --target "$TGT" --q-source "$QS" --aux-q 1 --aux-sh 0.5
fit S1 --target "$TGT" --q-source "$QS" --seed 1
fit X-B --target "$TGT" --q-source "$QS" --init "$RUNS/$BEST/model.pt" --rooms playout --epochs 3 --lr 3e-4
