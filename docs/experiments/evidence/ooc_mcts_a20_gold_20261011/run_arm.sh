#!/usr/bin/env bash
# usage: run_arm.sh ARM FORCE.csv SEEDS.txt -> one replay per seed (4 in parallel) into ~/g/out/ARM
# Pass 1: FORCE=force.csv, SEEDS = all 262 seeds of targets.csv.
# Pass 2: FORCE=force_fixed.csv, SEEDS=repaired_seeds.txt (pass-1 outputs of those seeds set aside).
set -u
ARM=$1; FORCE=$2; SEEDS=$3; OUT=$HOME/g/out/$ARM; mkdir -p "$OUT"
cd /home/user/sts_ai
cp "$SEEDS" "$OUT/seeds.txt"
one() {
  S=$1
  [ -f "$OUT/$S.rc" ] && return 0
  rm -f "$OUT/$S.csv" "$OUT/$S.jsonl"
  ( export ARM; source $HOME/g/env_common.sh
    export STRATEGIC_MCTS_FORCE=$FORCE STRATEGIC_MCTS_OUT=$OUT/$S.jsonl STRATEGIC_MCTS_SEED_SHIFT=3900000 STRATEGIC_MCTS_REPS=4
    bash tools/seed_guard.sh $HOME/g/one_combat strategicgen2 1 2000 20 "$OUT/$S.csv" "$S" > "$OUT/$S.log" 2>&1
    echo $? > "$OUT/$S.rc" )
}
export -f one; export ARM OUT FORCE
xargs -P 4 -I{} bash -c 'one {}' < "$OUT/seeds.txt"
date -u > "$OUT/DONE"
