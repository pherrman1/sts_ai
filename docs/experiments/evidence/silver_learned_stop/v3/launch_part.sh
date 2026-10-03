#!/usr/bin/env bash
# v3 live promotion run (PLAN.md): 4 disjoint parts of 256 seeds, 4 shards of 64
# per part, one CPU per shard; each shard runs the four arms in order.
#   part M (0..3): seeds 46000000+256M .. +255
# Usage: launch_part.sh M [BINARY_SOURCE] [OUT]   (run from a checkout of the plan commit)
set -u
M=$1
SRC=${2:-/mnt/project-files/silver-learned-stop/one_combat-8c7da1d0}
OUT=${3:-/mnt/project-files/silver-learned-stop/run3/part$M}
cd "$(git rev-parse --show-toplevel)"
EV=docs/experiments/evidence/silver_learned_stop
mkdir -p "$OUT"
# The shared folder is not executable: run a local copy, checked by hash.
BIN=$(mktemp -d)/one_combat
cp "$SRC" "$BIN" && chmod +x "$BIN"
echo "c43c9d1bab5d05e4c2d7823a330fc061217da702481cc982c83e02a1464cfd11  $BIN" | sha256sum -c - || exit 1
"$BIN" >/dev/null 2>&1; [ $? -ne 126 ] || { echo "binary not executable"; exit 1; }
export STS_EXECUTABLE_GIT_SHA=8c7da1d05293afa8c3b0e1288a9105d626b7ffa6
arm() {   # arm NAME K SEED_START
  local name=$1 k=$2 s=$3
  ( source $EV/live_env.sh
    case $name in
      control) export STS_SILVER_ADAPTIVE=1 ;;
      learned) export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1 ;;
      bossfallback) export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1 STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=1 ;;
      bossmax30k) export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1 STS_SILVER_LEARNED_STOP_BOSS_MAX=30000 ;;
    esac
    { time taskset -c $k bash tools/seed_guard.sh $BIN bestbench 10000 64 0 \
        $s $OUT/${name}$k.csv ; } > $OUT/${name}$k.log 2>&1
    echo "exit $?" >> $OUT/${name}$k.log )
}
for k in 0 1 2 3; do
  s=$((46000000 + 256*M + 64*k))
  ( for a in control learned bossfallback bossmax30k; do arm $a $k $s; done ) &
done
wait
echo "part $M done" > "$OUT/DONE"
