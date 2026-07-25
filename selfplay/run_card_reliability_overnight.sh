#!/usr/bin/env bash
set -euo pipefail

# Continue an already-running Panel A, then collect Panel B, analyze reliability,
# and only when labels are unstable collect a separate adaptive-futures dataset.
# Usage: run_card_reliability_overnight.sh PANEL_A_PID SERVER_PID
panel_a_pid=${1:?panel A pid required}
server_pid=${2:?v_server pid required}
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

status=selfplay/card_buffer/card_reliability_status.txt
panel_a=selfplay/card_buffer/card_reliability_a_120k_1k.csv
panel_b=selfplay/card_buffer/card_reliability_b_120k_1k.csv
metrics=selfplay/card_buffer/card_reliability_120k_1k_metrics.json
adaptive=selfplay/card_buffer/card_cf_adaptive_122k_2k.csv

cleanup() {
    if kill -0 "$server_pid" 2>/dev/null \
       && tr '\0' ' ' <"/proc/$server_pid/cmdline" 2>/dev/null | grep -q 'v_server.py'; then
        kill "$server_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "waiting_panel_a" >"$status"
while kill -0 "$panel_a_pid" 2>/dev/null; do sleep 30; done
../.venv/bin/python - "$panel_a" <<'PY'
import sys, pandas as pd
d = pd.read_csv(sys.argv[1])
if d.seed.nunique() != 1000 or d[["seed", "actionIdx", "candidateId", "candidateUpgraded"]].duplicated().any():
    raise SystemExit("panel A is incomplete or contains duplicate actions")
PY

echo "collecting_panel_b" >"$status"
OMP_NUM_THREADS=8 STS_FAIR=1 \
STS_VNET=selfplay/current/v_combat_trees.txt STS_VNET_ALPHA=0.3 \
STS_POLICY=selfplay/current/policy_trees_c.txt STS_SKIP_THR=-0.5 \
./one_combat_cardcf.elf datagen3 \
    1000 100 0 0.05 /tmp/card_reliability_meta_b.csv /tmp/card_reliability_rest_b.csv \
    121000 0 1 4 "$panel_b" 100 1000 4 1 1 2002
../.venv/bin/python - "$panel_b" <<'PY'
import sys, pandas as pd
d = pd.read_csv(sys.argv[1])
if d.seed.nunique() != 1000 or d[["seed", "actionIdx", "candidateId", "candidateUpgraded"]].duplicated().any():
    raise SystemExit("panel B is incomplete or contains duplicate actions")
PY

echo "analyzing" >"$status"
../.venv/bin/python analyze_card_cf_reliability.py "$panel_a" "$panel_b" "$metrics"

needs_adaptive=$(../.venv/bin/python -c \
    'import json,sys; print(int(json.load(open(sys.argv[1]))["needs_adaptive_futures"]))' "$metrics")
if [ "$needs_adaptive" -eq 1 ]; then
    echo "collecting_adaptive" >"$status"
    OMP_NUM_THREADS=8 STS_FAIR=1 \
    STS_VNET=selfplay/current/v_combat_trees.txt STS_VNET_ALPHA=0.3 \
    STS_POLICY=selfplay/current/policy_trees_c.txt STS_SKIP_THR=-0.5 \
    ./one_combat_cardcf.elf datagen3 \
        2000 100 0 0.05 /tmp/card_adaptive_meta.csv /tmp/card_adaptive_rest.csv \
        122000 0 1 4 "$adaptive" 100 1000 2 1 1 3003 8 5.0
    ../.venv/bin/python -c \
        'import json,sys,pandas as pd; d=pd.read_csv(sys.argv[1]); g=d.groupby(["seed","decisionIdx"]).first(); out={"decisions":len(g),"mean_futures":float(g.branchFutures.mean()),"future_counts":{str(int(k)):int(v) for k,v in g.branchFutures.value_counts().sort_index().items()}}; json.dump(out,open(sys.argv[2],"w"),indent=2); print(json.dumps(out,indent=2))' \
        "$adaptive" selfplay/card_buffer/card_cf_adaptive_122k_2k_summary.json
fi
echo "complete" >"$status"
