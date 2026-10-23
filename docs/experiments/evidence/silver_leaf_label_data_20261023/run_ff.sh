#!/usr/bin/env bash
# First-fight exact test of a leaf net on the Part B fights 111333000-099 (Cultist, Two Louse, Jaw Worm; the fresh
# block of ../leaf_head_turn_penalty_20261022), configs prod and prod@mb=4: ../leaf_head_turn_penalty_20261022/run_tp.sh
# plus --leaf-trunk, 2 shards per encounter, then ../silver_leaf_a20_data_20261022/analyze_oracle.py. Offline.
# usage (repo root): run_ff.sh BIN OUTDIR TAG MODES HEADS TRUNK
set -uo pipefail
BIN=$1 O=$2 TAG=$3 MODES=$4 HEADS=$5 TRUNK=$6
export STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 OMP_NUM_THREADS=1
mkdir -p "$O"; sha256sum "$BIN"; t0=$(date +%s)
for e in CULTIST TWO_LOUSE JAW_WORM; do
  for k in 0 1; do
    tools/seed_guard.sh "$BIN" 50 $((111333000 + 50 * k)) "$O/${TAG}_${e}_$k.jsonl" --encounter $e --abstract-only \
      --configs prod,prod@mb=4 --leaf-oracles "$MODES" --leaf-heads "$HEADS" --leaf-trunk "$TRUNK" \
      > "$O/${TAG}_${e}_$k.log" 2>&1 &
  done
done
wait
echo "$TAG wall=$(( $(date +%s) - t0 ))s summaries=$(cat "$O/${TAG}"_*.jsonl | grep -c '"summary"')" \
  "failures=$(cat "$O/${TAG}"_*.jsonl | grep -c '"failure"')"
SEEDS=111333000:111333099 python3 docs/experiments/evidence/silver_leaf_a20_data_20261022/analyze_oracle.py \
  "$O/${TAG}.json" "$O/${TAG}"_*.jsonl > "$O/${TAG}_analysis.txt" 2>&1
