#!/bin/bash
# §469 paired online check on the Collector: arm A = gen-4 MLP tree prior, arm B = Collector prior (§467).
# silverfocusevalgen: Collector forced as act-2 boss, reached with the gen-4 prior at 2k (root bonus on);
# then 8 copies of the fight, each played by both arms at 2k flat exact Silver, K=8, weight 400.
# 1,000 runs, seeds 99000000-99000999, in 250 units of 4 seeds. Lane L = 4(W-1)+i takes u = L mod 4N.
# Stall rule (automatic): a unit whose one_combat runs > 1800 s gets a gdb backtrace in
# OUT/<tag>.stall.txt and is killed (rc 137); no rerun. A failed unit does not stop the run.
# usage: bash worker.sh W N OUT_DIR ENV_SH    (N = 2, 4 or 8; ENV_SH = the checked local copy of env.sh)
set -euo pipefail
W="$1"; N="$2"; OUT="$3"; ENVSH="$4"
SHA=0ce7bc4ee47fb7c87518a44c4dd9778a65b5cbf5
BIN_SHA=755be7be8548f2c2b2e297296166295336fb90652cc9125c29aa97ae9e8502a7
ENV_SHA=a92be23874af1a69b1bb884b59025755c9a0296989014dd76f3743a72dac349a
A_SHA=3ebeab9d33e341735d9f4b61f7f50ab59b0c077286f62af13e9098bfdfc052d6
B_SHA=d78f80c904439129fc2b7856e57772b8b22a8b9eab47e87711a3fbc86491c881
UNITS=250; PER=4; BASE=99000000; STALL=1800
(( (N == 2 || N == 4 || N == 8) && W >= 1 && W <= N )) || { echo "bad W/N: $W/$N"; exit 1; }
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "checkout is not $SHA"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "tracked changes in checkout"; exit 1; }
RUN="$HOME/eval469-w$W"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
[ -e "$RUN" ] && [ -n "$(ls -A "$RUN" 2>/dev/null)" ] && { echo "RUN dir not empty: $RUN"; exit 1; }
mkdir -p "$OUT" "$RUN"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp /mnt/project-files/silver-az-mlp/gen4/model/combat_policy_mlp_gen4.txt "$RUN/"
cp /mnt/project-files/silver-prior-fight-specific/collector-data/result/combat_policy_mlp_collector467.txt "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$BIN_SHA"
check "$RUN/combat_policy_mlp_gen4.txt" "$A_SHA"
check "$RUN/combat_policy_mlp_collector467.txt" "$B_SHA"
check "$ENVSH" "$ENV_SHA"
sed "s#\$RUN#$RUN#g" "$ENVSH" > "$RUN/env.sh"
. "$RUN/env.sh"
echo "$BIN_SHA" > "$OUT/BINARY_SHA256"
lane() {
  local L=$1 u seed tag rc s pid
  for (( u = L; u < UNITS; u += 4 * N )); do
    seed=$(( BASE + PER * u )); tag="eval469-$seed"; s=$(date +%s); rc=0
    tools/seed_guard.sh "$RUN/one_combat" silverfocusevalgen "$PER" 0 "$OUT/$tag" "$seed" \
      COLLECTOR 8 2000 2000 8 "$RUN/combat_policy_mlp_gen4.txt" "$RUN/combat_policy_mlp_collector467.txt" \
      > "$OUT/$tag.log" 2>&1 &
    pid=$!
    while kill -0 "$pid" 2>/dev/null; do
      if (( $(date +%s) - s > STALL )); then
        gdb -p "$pid" -batch -ex "thread apply all bt" > "$OUT/$tag.stall.txt" 2>&1 || true
        kill -9 "$pid" 2>/dev/null || true
        echo "STALL $tag killed after ${STALL}s (backtrace $tag.stall.txt)" >> "$OUT/stalls.txt"
        break
      fi
      sleep 5
    done
    wait "$pid" || rc=$?
    if (( rc == 0 )); then touch "$OUT/$tag.done"; else for f in "$OUT/$tag".csv "$OUT/$tag".manifest.json; do [ -e "$f" ] && mv -f "$f" "$f.failed" || true; done; fi
    echo "$tag lane=$L rc=$rc wall=$(( $(date +%s) - s ))" >> "$OUT/units.txt"
  done
  echo "lane $L end" >> "$OUT/lanes.txt"
}
want=0
for i in 0 1 2 3; do
  L=$(( 4 * (W - 1) + i )); (( L < UNITS )) && want=$(( want + (UNITS - 1 - L) / (4 * N) + 1 ))
  lane "$L" &
done
wait
ok=$(grep -c " rc=0 " "$OUT/units.txt" || true)
[ "$ok" -eq "$want" ] && echo "W=$W N=$N units=$ok/$want done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
echo "WORKER_END units ok $ok of $want"
