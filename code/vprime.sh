#!/usr/bin/env bash
# V-prime (#1053): V recipe on D2 train + all of pack-g7f (g7f_E's own pack), with and without a 512/256 teacher.
WT=$HOME/sts-rolloutprior; RP=$HOME/rolloutprior; RUNS=$RP/runs
T=$WT/tools/rollout_prior/train.py; X=$HOME/Documents/sts/gen7-gpu/data/pack-g7f.npz
run() { local n=$1; shift
  [ -f $RUNS/$n/train.json ] && { echo "kept $n"; return; }
  python3 -P $T fit $RP/pack.npz $RUNS/$n --device cuda --threads 8 --target visits --q-source backed --extra-pack $X "$@" > $RUNS/$n.log 2>&1 || { echo "FAILED $n"; exit 1; }
  grep RESULT $RUNS/$n.log | cut -c1-300; echo "DONE $n"; }
run M
run T --h1 512 --h2 256 --lr 5e-4 --dropout 0.35 --dump-logp
run MT --teacher $RUNS/T --alpha 0.5
run MT-W256 --teacher $RUNS/T --alpha 0.5 --h1 256 --h2 128
echo VPRIME_DONE
