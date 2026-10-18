#!/usr/bin/env bash
# gate.sh BINDIR OUTDIR SEED STOP_AFTER_ACT
S=${S:?set S to a work dir holding bin/run_unit_prof.sh}
B=$1 O=$2 SEED=$3 STOP=$4
mkdir -p $O
sed -e "s|STS_STOP_AFTER_ACT=0|STS_STOP_AFTER_ACT=$STOP|" $S/bin/run_unit_prof.sh > $O/run_unit.sh
EXTRA="STS_RUN_PROFILE=$O/S-a20-$SEED.runprof.jsonl" bash $O/run_unit.sh /home/user/sts_ai $B $O S 20 $SEED
