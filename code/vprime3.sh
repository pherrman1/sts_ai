#!/usr/bin/env bash
# after vprime2.sh: MT-D2-W256 (256/128 student, D2, 0.5 visits + 0.5 softmax(T-D2)) only if MT-D2 ran.
WT=$HOME/sts-rolloutprior; RP=$HOME/rolloutprior; RUNS=$RP/runs; T=$WT/tools/rollout_prior/train.py
until grep -qE "VPRIME2_DONE|FAILED" $RP/vprime2.log; do sleep 30; done
grep -q FAILED $RP/vprime2.log && { echo "FAILED vprime2.sh, not starting"; exit 1; }
[ -f $RUNS/MT-D2/train.json ] || { echo "SKIP MT-D2-W256 (no MT-D2)"; echo VPRIME3_DONE; exit 0; }
python3 -P $T fit $RP/pack.npz $RUNS/MT-D2-W256 --device cuda --threads 8 --target visits --q-source backed --teacher $RUNS/T-D2 --alpha 0.5 --h1 256 --h2 128 > $RUNS/MT-D2-W256.log 2>&1 || { echo "FAILED MT-D2-W256"; exit 1; }
grep RESULT $RUNS/MT-D2-W256.log | cut -c1-300; echo "DONE MT-D2-W256"; echo VPRIME3_DONE
