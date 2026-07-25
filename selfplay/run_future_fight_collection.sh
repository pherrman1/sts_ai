#!/usr/bin/env bash
set -euo pipefail

# Collect direct counterfactual survival supervision for card rewards, then
# train the paired action model.  Each card/skip branch finishes its run under
# common RNG and records whether it clears the next battle, next routed elite,
# and current-act boss.  This is intentionally a NEW CSV: older card-CF files
# predate the probe columns and must not be appended to.
#
# Usage: run_future_fight_collection.sh N_RUNS SEED_OFFSET [TAG]
N_RUNS=${1:?usage: run_future_fight_collection.sh N_RUNS SEED_OFFSET [TAG]}
SEED_OFFSET=${2:?usage: run_future_fight_collection.sh N_RUNS SEED_OFFSET [TAG]}
TAG=${3:-future_fight}

SP=selfplay
DATA=$SP/card_buffer/card_cf_${TAG}.csv
META=$SP/card_buffer/card_cf_${TAG}_meta.csv
REST=$SP/card_buffer/card_cf_${TAG}_rest.csv
MAPS=$SP/card_buffer/card_cf_${TAG}_maps.csv
MODEL=$SP/card_models/card_cf_${TAG}
SERVER_LOG=$SP/card_buffer/card_cf_${TAG}_server.log
BIN=${STS_FUTURE_FIGHT_BIN:-./one_combat.elf}

export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-8}
export VWIN=$SP/current/v_win.json
export VPORT=${VPORT:-5555}

../.venv/bin/python v_server.py >"$SERVER_LOG" 2>&1 &
server_pid=$!
cleanup() {
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

ready=0
for attempt in $(seq 1 600); do
    if ! kill -0 "$server_pid" 2>/dev/null; then break; fi
    if bash -c 'exec 3<>/dev/tcp/127.0.0.1/"$1"' _ "$VPORT" 2>/dev/null; then ready=1; break; fi
    sleep 0.1
done
if [ "$ready" -ne 1 ]; then
    tail -n 100 "$SERVER_LOG"
    exit 1
fi

# A full continuation is essential: a three-fight horizon cannot label the
# current act's boss for early-card decisions.  Adaptive futures spend extra
# samples only when the full-run action gap is close.
STS_FAIR=1 \
STS_VNET=$SP/current/v_combat_trees.txt STS_VNET_ALPHA=0.3 \
STS_POLICY=$SP/current/policy_trees_c.txt STS_SKIP_THR=-0.5 \
"$BIN" datagen3 \
    "$N_RUNS" 100 0 0.05 "$META" "$REST" "$SEED_OFFSET" 0 1 4 \
    "$DATA" 100 1000 2 1 1 4101 8 5.0

../.venv/bin/python - "$DATA" <<'PY'
import sys
import pandas as pd

d = pd.read_csv(sys.argv[1], nrows=1)
need = {"branchNextCombatSeen", "branchNextCombatPassed",
        "branchNextEliteSeen", "branchNextElitePassed",
        "branchNextBossSeen", "branchNextBossPassed", "branchFutureComplete"}
missing = need - set(d.columns)
if missing:
    raise SystemExit("future-fight columns missing; rebuild one_combat before collecting: "
                     + ", ".join(sorted(missing)))
PY

"$BIN" mapbatch "$DATA" "$MAPS"
CARD_CF_DEVICE=cpu CARD_CF_INIT=build/v_deckset.pt \
CARD_CF_MIN_DECISIONS=100 CARD_CF_EPOCHS=60 CARD_CF_BATCH=256 \
../.venv/bin/python train_card_cf.py "$DATA" "$MODEL" build/v_rich_xgb.json "$MAPS"

printf 'complete tag=%s runs_added=%s seed_offset=%s\n' "$TAG" "$N_RUNS" "$SEED_OFFSET"
