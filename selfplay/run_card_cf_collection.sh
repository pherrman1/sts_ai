#!/usr/bin/env bash
set -euo pipefail

# Unattended paired card-reward collection followed by CPU-only action-value
# training.  The caller supplies collision-free source seeds after auditing the
# existing append-only buffer.
N_RUNS=${1:?usage: run_card_cf_collection.sh N_RUNS SEED_OFFSET [TAG]}
SEED_OFFSET=${2:?usage: run_card_cf_collection.sh N_RUNS SEED_OFFSET [TAG]}
TAG=${3:-full}

SP=selfplay
DATA=$SP/card_buffer/pilot_card_cf.csv
META=$SP/card_buffer/pilot_meta.csv
REST=$SP/card_buffer/pilot_rest.csv
MODEL=$SP/card_models/card_cf_${TAG}
SERVER_LOG=$SP/card_buffer/${TAG}_server.log

export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=8
export VWIN=$SP/current/v_win.json

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
    if bash -c 'exec 3<>/dev/tcp/127.0.0.1/5555' 2>/dev/null; then
        ready=1
        break
    fi
    sleep 0.1
done
if [ "$ready" -ne 1 ]; then
    tail -n 100 "$SERVER_LOG"
    exit 1
fi

STS_FAIR=1 \
STS_VNET=$SP/current/v_combat_trees.txt \
STS_VNET_ALPHA=0.3 \
STS_POLICY=$SP/current/policy_trees_c.txt \
STS_SKIP_THR=-0.5 \
./one_combat_cardcf.elf datagen3 \
    "$N_RUNS" 100 0 0.05 "$META" "$REST" "$SEED_OFFSET" 0 1 4 \
    "$DATA" 100 1000 2 1 1

CARD_CF_DEVICE=cpu \
CARD_CF_INIT=build/v_deckset.pt \
CARD_CF_MIN_DECISIONS=100 \
CARD_CF_EPOCHS=60 \
CARD_CF_BATCH=256 \
../.venv/bin/python train_card_cf.py \
    "$DATA" "$MODEL" build/v_rich_xgb.json

printf 'complete tag=%s runs_added=%s seed_offset=%s\n' "$TAG" "$N_RUNS" "$SEED_OFFSET"
