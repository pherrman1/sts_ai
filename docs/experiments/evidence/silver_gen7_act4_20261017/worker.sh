#!/bin/bash
# Silver prior gen 7, Act-4 self-play worker (PLAN.md): 4 lanes on 4 cores.
# silverazact4gen at 40k, 2 copies per state, gen-6 MLP g6_E as tree prior K=8, weight 400, root bonus off.
# STATES (act4-states.jsonl, usable Act-4 CTM label rows only) is cut into units of 25 states; unit u holds
# lines 25u+1..25u+25 and uses seeds SEED0 + 25u .. (state i of the file has seed SEED0 + i).
# Lane L = 4(W-1)+i takes units u = L mod 4N. Stall rule: a unit running > 7200 s gets a gdb backtrace
# in OUT/<tag>.stall.txt and is killed (rc 137); no rerun. A failed unit does not stop the run.
# usage: bash worker.sh W N OUT_DIR STATES    (run from the repository checkout at RUN_COMMIT)
set -euo pipefail
W="$1"; N="$2"; OUT="$3"; STATES="$4"
SHA=__RUN_COMMIT__
BIN_SHA=__BIN_SHA__
STATES_SHA=__STATES_SHA__
PRIOR=docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt
PRIOR_SHA=ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228
PER=25; SEED0=111170200; SEEDMAX=111179999; COPIES=2; SIMS=40000; STALL=7200
[[ "$W" =~ ^[1-9][0-9]*$ && "$N" =~ ^[1-9][0-9]*$ ]] || { echo "bad W/N: $W/$N (unpadded integers)"; exit 1; }
(( W <= N && N <= 16 )) || { echo "bad W/N: $W/$N"; exit 1; }
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "checkout is not $SHA"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "tracked changes in checkout"; exit 1; }
RUN="$HOME/gen7a4-w$W"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
[ -e "$RUN" ] && [ -n "$(ls -A "$RUN" 2>/dev/null)" ] && { echo "RUN dir not empty: $RUN"; exit 1; }
mkdir -p "$OUT" "$RUN/raw" "$RUN/units"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp "$PRIOR" "$RUN/prior.txt"
cp "$STATES" "$RUN/states.jsonl"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$BIN_SHA"
check "$RUN/prior.txt" "$PRIOR_SHA"
check "$RUN/states.jsonl" "$STATES_SHA"
S=$(wc -l < "$RUN/states.jsonl")
UNITS=$(( (S + PER - 1) / PER ))
(( S >= 1 && SEED0 + S - 1 <= SEEDMAX )) || { echo "bad state count $S"; exit 1; }
export STS_EXECUTABLE_GIT_SHA="$SHA" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated
export STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 STS_SILVER_VNET_LEAF_DIRECT=0
export STS_SILVER_ROOT_PRIOR="$RUN/prior.txt" STS_SILVER_ROOT_PRIOR_WEIGHT=400
echo "$BIN_SHA" > "$OUT/BINARY_SHA256"
lane() {
  local L=$1 u n seed tag rc s pid
  for (( u = L; u < UNITS; u += 4 * N )); do
    seed=$(( SEED0 + PER * u )); n=$(( S - PER * u < PER ? S - PER * u : PER ))
    tag="act4-$seed"; s=$(date +%s); rc=0
    sed -n "$(( PER * u + 1 )),$(( PER * u + n ))p" "$RUN/states.jsonl" > "$RUN/units/$tag.jsonl"
    tools/seed_guard.sh "$RUN/one_combat" silverazact4gen "$n" "$RUN/units/$tag.jsonl" "$SIMS" "$RUN/raw/$tag" \
      "$seed" "$COPIES" 8 0 > "$OUT/$tag.log" 2>&1 &
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
    echo "$tag lane=$L states=$n rc=$rc wall=$(( $(date +%s) - s ))" >> "$OUT/units.txt"
  done
  echo "lane $L end" >> "$OUT/lanes.txt"
}
want=0
for (( u = 4 * (W - 1); u < UNITS; u += 1 )); do (( u % (4 * N) < 4 * W && u % (4 * N) >= 4 * (W - 1) )) && want=$(( want + 1 )); done
(( want > 0 )) || { echo "no units for W=$W"; exit 1; }
for i in 0 1 2 3; do lane $(( 4 * (W - 1) + i )) & done
wait
ok=$(grep -c " rc=0 " "$OUT/units.txt" || true)
[ "$ok" -eq "$want" ] && echo "W=$W N=$N units=$ok/$want done $(date -u +%FT%TZ)" > "$OUT/DONE.txt"
echo "WORKER_END units ok $ok of $want"
