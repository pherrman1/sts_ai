#!/bin/bash
# Fight-specific Silver prior (§467): Collector-only self-play data worker, 4 lanes on 4 cores.
# silverazfocusgen at 10k, gen-4 MLP tree prior K=8, weight 400, root bonus off; Collector forced as
# act-2 boss; 4 recorded copies of the Collector fight (1 unperturbed + 3 perturbed); other fights 2k.
# 2,560 runs, seeds 95000000-95002559, in 640 units of 4 seeds. Lane L = 4(W-1)+i takes u = L mod 4N.
# Stall rule (automatic): a unit whose one_combat runs > 900 s gets a gdb backtrace in
# OUT/<tag>.stall.txt and is killed (rc 137); no rerun. A failed unit does not stop the run.
# usage: bash worker.sh W N OUT_DIR ENV_SH    (N = 4, 8 or 16; ENV_SH = the checked local copy of env.sh)
set -euo pipefail
W="$1"; N="$2"; OUT="$3"; ENVSH="$4"
SHA=1518989bded26cff6692373d367424c2ebd16845
BIN_SHA=ad90e6981dba8934dde825e3b181cb2072a783c119951ca81f57b5da83ea5493
ENV_SHA=63ff2137a299ee93c0e32fd723d06721fac3295af7a95e94ac7ea28b310db030
MODEL_SHA=3ebeab9d33e341735d9f4b61f7f50ab59b0c077286f62af13e9098bfdfc052d6
UNITS=640; PER=4; BASE=95000000; STALL=900
(( (N == 4 || N == 8 || N == 16) && W >= 1 && W <= N )) || { echo "bad W/N: $W/$N"; exit 1; }
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "checkout is not $SHA"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "tracked changes in checkout"; exit 1; }
RUN="$HOME/collector-w$W"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
[ -e "$RUN" ] && [ -n "$(ls -A "$RUN" 2>/dev/null)" ] && { echo "RUN dir not empty: $RUN"; exit 1; }
mkdir -p "$OUT" "$RUN/raw"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp /mnt/project-files/silver-az-mlp/gen4/model/combat_policy_mlp_gen4.txt "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$BIN_SHA"
check "$RUN/combat_policy_mlp_gen4.txt" "$MODEL_SHA"
check "$ENVSH" "$ENV_SHA"
sed "s#\$RUN#$RUN#g" "$ENVSH" > "$RUN/env.sh"
. "$RUN/env.sh"
echo "$BIN_SHA" > "$OUT/BINARY_SHA256"
lane() {
  local L=$1 u seed tag rc s pid
  for (( u = L; u < UNITS; u += 4 * N )); do
    seed=$(( BASE + PER * u )); tag="collector-$seed"; s=$(date +%s); rc=0
    tools/seed_guard.sh "$RUN/one_combat" silverazfocusgen "$PER" 10000 0 "$RUN/raw/$tag" "$seed" \
      COLLECTOR 4 2000 8 0 > "$OUT/$tag.log" 2>&1 &
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
