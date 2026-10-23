#!/bin/bash
# Exact first fights with leaf heads (PREREG.md): replays FIRST..FIRST+N-1 of Cultist, Two Louse and Jaw Worm in SHARDS
# shards per encounter, configs prod and prod@mb=4, the given --leaf-oracles modes and --leaf-heads.
# usage (repo root): run_tp.sh BIN OUTDIR TAG FIRST N SHARDS MODES HEADS
BIN=$1; OUT=$2; TAG=$3; FIRST=$4; N=$5; SHARDS=$6; MODES=$7; HEADS=$8
export STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 OMP_NUM_THREADS=1
H=(); [ -n "$HEADS" ] && H=(--leaf-heads "$HEADS")
mkdir -p "$OUT"; t0=$(date +%s); K=$((N / SHARDS))
for e in CULTIST TWO_LOUSE JAW_WORM; do
  for k in $(seq 0 $((SHARDS - 1))); do
    tools/seed_guard.sh "$BIN" $K $((FIRST + K * k)) "$OUT/${TAG}_${e}_$k.jsonl" --encounter $e --abstract-only \
      --configs prod,prod@mb=4 --leaf-oracles "$MODES" "${H[@]}" > "$OUT/${TAG}_${e}_$k.log" 2>&1 &
  done
done
wait
echo "$TAG wall=$(( $(date +%s) - t0 ))s summaries=$(cat "$OUT/${TAG}"_*.jsonl | grep -c '"summary"')" \
  "failures=$(cat "$OUT/${TAG}"_*.jsonl | grep -c '"failure"')"
