#!/usr/bin/env bash
# queued after vprime.sh: T-D2 (512/256 teacher, T's recipe, D2 only); MT-D2 if T-D2 beats W256 (1.849).
WT=$HOME/sts-rolloutprior; RP=$HOME/rolloutprior; RUNS=$RP/runs; T=$WT/tools/rollout_prior/train.py
until grep -qE "VPRIME_DONE|FAILED" $RP/vprime.log; do sleep 30; done
grep -q FAILED $RP/vprime.log && { echo "FAILED vprime.sh, not starting"; exit 1; }
run() { local n=$1; shift
  [ -f $RUNS/$n/train.json ] && { echo "kept $n"; return; }
  python3 -P $T fit $RP/pack.npz $RUNS/$n --device cuda --threads 8 --target visits --q-source backed "$@" > $RUNS/$n.log 2>&1 || { echo "FAILED $n"; exit 1; }
  grep RESULT $RUNS/$n.log | cut -c1-300; echo "DONE $n"; }
run T-D2 --h1 512 --h2 256 --lr 5e-4 --dropout 0.35 --dump-logp
pl=$(python3 -c "import json;print(json.load(open('$RUNS/T-D2/train.json'))['val_final']['playout']['q_regret_backed'])")
echo "T-D2 playout backed $pl"
if python3 -c "import sys;sys.exit(0 if $pl < 1.849 else 1)"; then run MT-D2 --teacher $RUNS/T-D2 --alpha 0.5; else echo "SKIP MT-D2 (T-D2 not below W256 1.849)"; fi
echo VPRIME2_DONE
