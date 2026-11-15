#!/bin/bash
# issue #1050 stage 0, PREREG docs/experiments/evidence/critic_encounters_20261115 (worktree ~/sts-critic-enc @75cdc2d1)
set -u
cd ~/sts-critic-enc
O=~/critic-enc-out; P=/home/philippherrmann/ppo-longb/LONG_C/parts
ENC=$O/critic_encounters_long_c_220_419.json.gz
TRAIN=("$P/traj-02[2-9]?-p*.jsonl.gz" "$P/traj-03??-p*.jsonl.gz"); TEST=("$P/traj-04[01]?-p*.jsonl.gz")
PY=/usr/bin/python3; T=tools/heart1/critic_ceiling.py; L=$O/commands.log
log(){ echo "$(date -Iseconds) $*" >> $L; }
log "# commit $(git rev-parse HEAD); python $PY; $($PY -c 'import xgboost,numpy,scipy;print("xgboost",xgboost.__version__,"numpy",numpy.__version__,"scipy",scipy.__version__)')"
log "# table sha256 $(sha256sum $ENC | cut -d' ' -f1)"
run(){ # name, cmd...  ; kills the job if MemAvailable < 4096 MB
  local name=$1; shift; log "START $name: $*"; local t0=$(date +%s)
  nice -n 10 "$@" & local pid=$!
  while kill -0 $pid 2>/dev/null; do
    local m=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    if [ "$m" -lt 4096 ]; then log "KILL $name: MemAvailable $m MB < 4096 MB"; kill -9 $pid; fi; sleep 5; done
  wait $pid; local rc=$?; log "END $name rc=$rc wall=$(( $(date +%s)-t0 ))s"; return $rc; }
fits(){ local frac=$1
  run fit_gbm_$frac $PY $T fit-gbm --train "${TRAIN[@]}" --exclude-from "${TEST[@]}" --per-game 8 --game-frac $frac --threads 4 --workers 4 --out $O/gbm.json || return 1
  run fit_gbm_enc_$frac $PY $T fit-gbm --train "${TRAIN[@]}" --exclude-from "${TEST[@]}" --per-game 8 --game-frac $frac --threads 4 --workers 4 --encounters $ENC --enc-scope act --out $O/gbm_enc.json || return 1
  run fit_gbm_run_$frac $PY $T fit-gbm --train "${TRAIN[@]}" --exclude-from "${TEST[@]}" --per-game 8 --game-frac $frac --threads 4 --workers 4 --encounters $ENC --enc-scope run --out $O/gbm_run.json || return 1; }
if ! fits 1.0; then log "NOTE a fit failed at game-frac 1.0; PREREG fallback: all three fits at 0.5"; fits 0.5 || { log "ABORT fits failed at 0.5"; exit 1; }; fi
log "FITS DONE"
run eval $PY $T evaluate --test "${TEST[@]}" --gbm $O/gbm.json --extra-gbm gbm_enc=$O/gbm_enc.json --extra-gbm gbm_run=$O/gbm_run.json --encounters $ENC --contrast gbm_enc:gbm --contrast gbm_enc:online_cal --contrast gbm_run:gbm --contrast gbm_run:gbm_enc --rule encounters --enc-ev-margin 0.03 --train-seeds-from "${TRAIN[@]}" --out $O/report.json
log "EVAL DONE"
