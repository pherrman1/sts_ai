#!/usr/bin/env bash
# L512: 512/256, V/W256 recipe, D2 only. L1024 (1024/512) only if L512 beats W256 (1.849) by more than 0.009.
RP=$HOME/rolloutprior; RUNS=$RP/runs; T=$HOME/sts-rolloutprior/tools/rollout_prior/train.py
run() { local n=$1; shift
  python3 -P $T fit $RP/pack.npz $RUNS/$n --device cuda --threads 8 --target visits --q-source backed "$@" > $RUNS/$n.log 2>&1 || { echo "FAILED $n"; exit 1; }
  grep RESULT $RUNS/$n.log | cut -c1-300; echo "DONE $n"; }
run L512 --h1 512 --h2 256
pl=$(python3 -c "import json;print(json.load(open('$RUNS/L512/train.json'))['val_final']['playout']['q_regret_backed'])"); echo "L512 playout backed $pl"
if python3 -c "import sys;sys.exit(0 if $pl < 1.8491 - 0.009 else 1)"; then run L1024 --h1 1024 --h2 512; else echo "SKIP L1024"; fi
echo LARGE_DONE
