#!/bin/bash
# Silver AZ MLP loop, generation-6 self-play worker: 4 lanes on 4 cores.
# silverazgen at 40k, gen-5 MLP tree prior K=8, weight 400, root bonus off (PLAN §2.2).
# 1,024 runs in 256 units of 4 seeds: units 0-127 natural (97000000-97000511),
# units 128-255 perturbed (97001000-97001511). Lane L = 4(W-1)+i takes units u = L mod 4N.
# Stall rule (automatic): a unit whose one_combat runs > 7200 s gets a gdb backtrace in
# OUT/<tag>.stall.txt and is killed (rc 137); no rerun. A failed unit does not stop the run.
# usage: bash worker.sh W N OUT_DIR ENV_SH    (N = 4, 8 or 16; ENV_SH = the checked local copy of env.sh)
set -euo pipefail
W="$1"; N="$2"; OUT="$3"; ENVSH="$4"
SHA=f73e6ad709439ceb5c39164ae07836339dd20c92
BIN_SHA=b4586cfc0e26dcae96d3fe14f0c80beccd297cde87bd986fd69954cf126995e1
ENV_SHA=b9e62ec5fce56c3b6c1e703d12176ef71b3f25bf1ba3de7aec7eff664bd23370
MODEL_SHA=5e9f975a35c0277e773fc0fc6d5f21564d75a66918e655f695f6efd1aac89e8a
UNITS=256; PER=4; NAT=97000000; PERT=97001000; STALL=7200
(( (N == 4 || N == 8 || N == 16) && W >= 1 && W <= N )) || { echo "bad W/N: $W/$N"; exit 1; }
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "checkout is not $SHA"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "tracked changes in checkout"; exit 1; }
RUN="$HOME/azgen6-w$W"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
[ -e "$RUN" ] && [ -n "$(ls -A "$RUN" 2>/dev/null)" ] && { echo "RUN dir not empty: $RUN"; exit 1; }
mkdir -p "$OUT" "$RUN/raw"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp /mnt/project-files/silver-az-mlp/gen5/model/combat_policy_mlp_gen5.txt "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$BIN_SHA"
check "$RUN/combat_policy_mlp_gen5.txt" "$MODEL_SHA"
check "$ENVSH" "$ENV_SHA"
sed "s#\$RUN#$RUN#g" "$ENVSH" > "$RUN/env.sh"
. "$RUN/env.sh"
echo "$BIN_SHA" > "$OUT/BINARY_SHA256"
lane() {
  local L=$1 u variant seed tag rc s pid
  for (( u = L; u < UNITS; u += 4 * N )); do
    if (( u < 128 )); then variant=natural; seed=$(( NAT + PER * u ));
    else variant=perturbed; seed=$(( PERT + PER * (u - 128) )); fi
    tag="$variant-$seed"; s=$(date +%s); rc=0
    tools/seed_guard.sh "$RUN/one_combat" silverazgen "$PER" 40000 0 "$RUN/raw/$tag" "$seed" "$variant" 8 0 \
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
    if (( rc == 0 )); then
      gzip -c "$RUN/raw/$tag.jsonl" > "$OUT/$tag.jsonl.gz"
      cp "$RUN/raw/$tag.manifest.json" "$RUN/raw/$tag.jsonl.provenance.json" "$OUT/"
      rm -f "$RUN/raw/$tag.jsonl"; touch "$OUT/$tag.done"
    fi
    echo "$tag lane=$L rc=$rc wall=$(( $(date +%s) - s ))" >> "$OUT/units.txt"
  done
  echo "lane $L end" >> "$OUT/lanes.txt"
}
for i in 0 1 2 3; do lane $(( 4 * (W - 1) + i )) & done
wait
want=$(( UNITS / N ))
ok=$(grep -c " rc=0 " "$OUT/units.txt" || true)
[ "$ok" -eq "$want" ] && echo "W=$W N=$N units=$ok/$want done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
echo "WORKER_END units ok $ok of $want"
