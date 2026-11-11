#!/usr/bin/env bash
# T1 grid of the Gumbel distillation plan (docs/experiments/evidence/gumbel_distill_t1_20261111/PREREG.md).
# usage: t1_grid.sh D2_TENSOR_DIR N_D0_CKPT POLONLY_D0_CKPT OUT_DIR [PHASE [GEN_ID]]
#   PHASE 1 (default): P-V, P-CQm, P-CQb, N (learning curves at F = 0.25 / 0.5 / 1), the S2 seed repeats, and every
#     policy run's final checkpoint re-scored under the other q source.
#   PHASE 2 GEN_ID: per-boss specialists fine-tuned from OUT/GEN_ID (P-V_f1 or P-CQb_f1, the better generalist),
#     each next to GEN_ID evaluated on the same boss rows.
# F < 1 runs train 3 / F epochs, so every run takes about as many steps as F = 1. Skips runs whose eval.json exists.
set -euo pipefail
DATA=$1; NCK=$2; PCK=$3; OUT=$4; PHASE=${5:-1}; GEN=${6:-}
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-python3 -P}
W=${WORKERS:-11}
run() {   # id init extra-args...
    local id=$1 init=$2; shift 2
    [ -f "$OUT/$id/eval.json" ] && { echo "skip $id"; return; }
    mkdir -p "$OUT/$id"
    echo "== $id $*"
    $PY "$HERE/train.py" "$DATA" "$OUT/$id" --init "$init" --eval-every 2000 --workers "$W" "$@" > "$OUT/$id/stdout.txt" 2>&1
    tail -1 "$OUT/$id/stdout.txt"
}
ep() { python3 -c "print(3 / $1)"; }
other() { [ "$1" = mean ] && echo backed || echo mean; }
BOSSES="HEXAGHOST SLIME_BOSS THE_GUARDIAN AUTOMATON CHAMP COLLECTOR AWAKENED_ONE DONU_AND_DECA TIME_EATER SHIELD_AND_SPEAR THE_HEART"
if [ "$PHASE" = 1 ]; then
    for F in 1 0.5 0.25; do
        run "P-V_f$F" "$PCK" --no-value --train-frac "$F" --epochs "$(ep "$F")" --q-source backed
        run "P-CQb_f$F" "$PCK" --no-value --policy-target cq:20 --q-source backed --train-frac "$F" --epochs "$(ep "$F")"
        run "N_f$F" "$NCK" --value-weight 0.25 --train-frac "$F" --epochs "$(ep "$F")" --q-source backed
    done
    run "P-CQm_f1" "$PCK" --no-value --policy-target cq:20 --q-source mean --epochs 3
    run "S2_P-V_f1" "$PCK" --no-value --epochs 3 --q-source backed --seed 20261109
    run "S2_P-CQb_f1" "$PCK" --no-value --policy-target cq:20 --q-source backed --epochs 3 --seed 20261109
    run "S2_N_f1" "$NCK" --value-weight 0.25 --epochs 3 --q-source backed --seed 20261109
    # re-score every final checkpoint under the other q source (q_regret / top1_qpick under mean and backed Q)
    for id in P-V_f1 P-V_f0.5 P-V_f0.25 P-CQb_f1 P-CQb_f0.5 P-CQb_f0.25 S2_P-V_f1 S2_P-CQb_f1; do
        run "EV-mean_$id" "$OUT/$id/model.pt" --no-value --eval-only --q-source mean
    done
    run "EV-backed_P-CQm_f1" "$OUT/P-CQm_f1/model.pt" --no-value --eval-only --q-source backed
elif [ "$PHASE" = 2 ]; then
    [ -n "$GEN" ] && [ -f "$OUT/$GEN/model.pt" ] || { echo "phase 2 needs GEN_ID with $OUT/GEN_ID/model.pt"; exit 2; }
    T=visits; [[ "$GEN" == *CQb* ]] && T=cq:20
    for e in $BOSSES; do
        run "GEN-${GEN}_$e" "$OUT/$GEN/model.pt" --no-value --eval-only --q-source backed --encounters "$e"
        run "SPEC_$e" "$OUT/$GEN/model.pt" --no-value --policy-target "$T" --q-source backed --encounters "$e" --epochs 3
        run "S2_SPEC_$e" "$OUT/$GEN/model.pt" --no-value --policy-target "$T" --q-source backed --encounters "$e" \
            --epochs 3 --seed 20261109
    done
else
    echo "unknown phase $PHASE"; exit 2
fi
echo "T1 phase $PHASE done"
