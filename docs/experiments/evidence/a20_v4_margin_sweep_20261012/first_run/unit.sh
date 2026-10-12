#!/usr/bin/env bash
# unit.sh LO N OUTDIR
R=$HOME/a20v4a0; LO=$1 N=$2 OUT=$3; base=$OUT/u-$LO
source $R/env.sh; mapfile -t E < <(arm_env $base $R)
cd /home/user/sts_ai
env -i "${E[@]}" timeout 6h bash tools/seed_guard.sh $R/one_combat bestbench 10000 $N 0 $LO $base.csv > $base.log 2>&1
echo "lo=$LO n=$N rc=$?" > $base.done
