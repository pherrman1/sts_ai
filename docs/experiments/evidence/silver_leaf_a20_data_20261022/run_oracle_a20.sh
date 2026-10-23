#!/bin/bash
# README step 4: a leaf head as Silver's leaf on the held-out exact first fights (replays 111149650-699; Cultist, Two
# Louse, Jaw Worm), configs prod and prod@mb=4, modes head:NAME and hblend:NAME:0.5. The none/exact/head:ct rows come
# from the capacity-test runs (same solver binary exact_combat_solver_ct, same seeds and settings), so all pair by seed.
# usage (repo root): run_oracle_a20.sh BIN NAME HEAD.txt OUTDIR
BIN=$1; NAME=$2; HEAD=$3; OUT=$4
export STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 OMP_NUM_THREADS=1
mkdir -p "$OUT"; t0=$(date +%s)
for e in CULTIST TWO_LOUSE JAW_WORM; do
  tools/seed_guard.sh "$BIN" 50 111149650 "$OUT/${NAME}_$e.jsonl" --encounter $e --abstract-only --configs prod,prod@mb=4 \
    --leaf-oracles head:$NAME,hblend:$NAME:0.5 --leaf-heads $NAME=$HEAD > "$OUT/${NAME}_$e.log" 2>&1 &
done
wait
echo "$NAME wall=$(( $(date +%s) - t0 ))s summaries=$(cat "$OUT/${NAME}"_*.jsonl | grep -c '"summary"')" \
  "failures=$(cat "$OUT/${NAME}"_*.jsonl | grep -c '"failure"')"
