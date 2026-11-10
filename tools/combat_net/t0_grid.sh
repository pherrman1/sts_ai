#!/usr/bin/env bash
# T0 grid of the Gumbel distillation plan (docs/experiments/evidence/gumbel_distill_t0_20261110/PREREG.md).
# usage: t0_grid.sh D1_TENSOR_DIR N_D0_CKPT POLONLY_D0_CKPT OUT_DIR [PHASE]
#   PHASE 1 (default): LC-N, LC-P, TG and the S2 seed repeats; PHASE 2 TARGET: LC-T with TARGET (e.g. cq:20);
#   PHASE 3: boss specialists (PREREG amendment 1), compared with LC-P_f1 evaluated on the boss rows.
# Every run fine-tunes a D0 checkpoint for ~5,300 steps (epochs 3 / F). Skips runs whose eval.json exists.
set -euo pipefail
DATA=$1; NCK=$2; PCK=$3; OUT=$4; PHASE=${5:-1}; TARGET=${6:-}
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-python3 -P}
W=${WORKERS:-11}
run() {   # id init extra-args...
    local id=$1 init=$2; shift 2
    [ -f "$OUT/$id/eval.json" ] && { echo "skip $id"; return; }
    mkdir -p "$OUT/$id"
    echo "== $id $*"
    $PY "$HERE/train.py" "$DATA" "$OUT/$id" --init "$init" --eval-every 500 --workers "$W" "$@" > "$OUT/$id/stdout.txt" 2>&1
    tail -1 "$OUT/$id/stdout.txt"
}
ep() { python3 -c "print(3 / $1)"; }
if [ "$PHASE" = 1 ]; then
    for F in 1 0.5 0.25 0.125; do
        run "LC-N_f$F" "$NCK" --value-weight 0.25 --train-frac "$F" --epochs "$(ep "$F")"
        run "LC-P_f$F" "$PCK" --no-value --train-frac "$F" --epochs "$(ep "$F")"
    done
    for T in cq:paper cq:5 cq:20; do
        run "TG_${T/:/-}" "$PCK" --no-value --policy-target "$T" --epochs 3
    done
    run "S2_LC-N_f1" "$NCK" --value-weight 0.25 --epochs 3 --seed 20261109
    run "S2_LC-P_f1" "$PCK" --no-value --epochs 3 --seed 20261109
    for T in cq:paper cq:5 cq:20; do
        run "S2_TG_${T/:/-}" "$PCK" --no-value --policy-target "$T" --epochs 3 --seed 20261109
    done
elif [ "$PHASE" = 3 ]; then
    G="$OUT/LC-P_f1/model.pt"
    [ -f "$G" ] || { echo "phase 3 needs $G"; exit 2; }
    run "BOSS-GEN_eval" "$G" --no-value --rooms 2 --eval-only
    run "BOSS-P_e3" "$PCK" --no-value --rooms 2 --epochs 3
    run "BOSS-P_e11" "$PCK" --no-value --rooms 2 --epochs 11
    run "BOSS-FT_e3" "$G" --no-value --rooms 2 --epochs 3
    run "S2_BOSS-P_e11" "$PCK" --no-value --rooms 2 --epochs 11 --seed 20261109
    run "S2_BOSS-FT_e3" "$G" --no-value --rooms 2 --epochs 3 --seed 20261109
else
    [ -n "$TARGET" ] || { echo "phase 2 needs TARGET"; exit 2; }
    for F in 0.5 0.25 0.125; do
        run "LC-T_f$F" "$PCK" --no-value --policy-target "$TARGET" --train-frac "$F" --epochs "$(ep "$F")"
    done
fi
echo "T0 phase $PHASE done"
