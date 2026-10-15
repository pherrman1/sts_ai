#!/usr/bin/env bash
# Pilot run (PLAN.md): seeds 57000000..57000127, 4 shards of 32 seeds, one CPU each.
# Each shard runs the three arms; shard k starts the arm list at position k mod 3.
# Usage: launch.sh BINARY BINARY_SHA256 BUILD_GIT_SHA OUT   (run from a checkout of the plan commit)
#        launch.sh BINARY BINARY_SHA256 BUILD_GIT_SHA OUT smoke   (seed 57009000, every arm, not pooled)
set -u
SRC=$1 SHA=$2 BUILD_SHA=$3 OUT=$4 MODE=${5:-run}
if env | grep -q '^STS_'; then echo "refusing: STS_* already exported" >&2; exit 1; fi
cd "$(git rev-parse --show-toplevel)"
EV=docs/experiments/evidence/ooc_mcts_f2_leaf_pilot_20261008
if [ -n "$(git status --porcelain)" ]; then echo "refusing: dirty checkout" >&2; exit 1; fi
mkdir -p "$OUT"
{ echo "plan_commit $(git rev-parse HEAD)"
  sha256sum models/candidates/v_win_x2b_trees.txt models/candidates/v_win_f2_e3_trees.txt \
    models/v_win_trees.txt selfplay/models/ooc_strategic_tok_final.native; } > "$OUT/provenance.txt"
BIN=$(mktemp -d)/one_combat   # /mnt/project-files is noexec: run a hash-checked local copy
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "$SHA  $BIN" | sha256sum -c - || exit 1
export STS_EXECUTABLE_GIT_SHA=$BUILD_SHA
ARMS=(flat10k x2b f2)
run_arm() {   # run_arm NAME CPU SEED_START COUNT TAG
  ( source $EV/arm_env.sh && arm_env $1 || exit 1
    { time taskset -c $2 bash tools/seed_guard.sh $BIN bestbench 10000 $4 0 \
        $3 $OUT/$1$5.csv ; } > $OUT/$1$5.log 2>&1
    echo "exit $?" >> $OUT/$1$5.log )
}
if [ "$MODE" = smoke ]; then
  for i in 0 1 2; do run_arm ${ARMS[$i]} $i 57009000 1 smoke & done
  wait; echo "smoke done" > "$OUT/SMOKE_DONE"; exit 0
fi
for k in 0 1 2 3; do
  s=$((57000000 + 32*k))
  ( for i in 0 1 2; do run_arm ${ARMS[$(( (i + k) % 3 ))]} $k $s 32 $k; done ) &
done
wait
echo "run done" > "$OUT/DONE"
