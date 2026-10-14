#!/bin/bash
# Silver AZ MLP loop, generation-4 self-play worker: 4 lanes on 4 cores.
# silverazgen at 10k, gen-3 MLP tree prior K=8, weight 400, root bonus off (PLAN §2.2).
# 1,024 runs in 256 units of 4 seeds: units 0-127 natural (91000000-91000511),
# units 128-255 perturbed (91001000-91001511). Lane L = 4(W-1)+i takes units u = L mod 4N.
# usage: bash worker.sh W N OUT_DIR    (N = 4, 8 or 16)
# Run from a detached checkout of f73e6ad709439ceb5c39164ae07836339dd20c92 after
# `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`.
set -euo pipefail
W="$1"; N="$2"; OUT="$3"
D=/mnt/project-files/silver-az-mlp/gen4
SHA=f73e6ad709439ceb5c39164ae07836339dd20c92
UNITS=256; PER=4; NAT=91000000; PERT=91001000
(( (N == 4 || N == 8 || N == 16) && W >= 1 && W <= N )) || { echo "bad W/N: $W/$N"; exit 1; }
REPO="$(git rev-parse --show-toplevel)"; cd "$REPO"
[ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "checkout is not $SHA"; exit 1; }
RUN="$HOME/azgen4-w$W"; mkdir -p "$RUN/raw"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && { echo "OUT not empty: $OUT"; exit 1; }
mkdir -p "$OUT"
cp build/linux-gcc-release/one_combat "$RUN/one_combat"
cp /mnt/project-files/silver-az-mlp/gen3/model/combat_policy_mlp_gen3.txt "$RUN/"
check() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || { echo "sha256 mismatch: $1"; exit 1; }; }
check "$RUN/one_combat" "$(cat "$D/BINARY_SHA256")"
check "$RUN/combat_policy_mlp_gen3.txt" f57b7fdd728a4086a00ac7fd6eafa5d393723789d38a330bf676599ef0da5315
sed "s#\$RUN#$RUN#g" "$D/env.sh" > "$RUN/env.sh"
. "$RUN/env.sh"
lane() {
  local L=$1 u variant seed tag rc s
  for (( u = L; u < UNITS; u += 4 * N )); do
    if (( u < 128 )); then variant=natural; seed=$(( NAT + PER * u ));
    else variant=perturbed; seed=$(( PERT + PER * (u - 128) )); fi
    tag="$variant-$seed"; s=$(date +%s); rc=0
    tools/seed_guard.sh "$RUN/one_combat" silverazgen "$PER" 10000 0 "$RUN/raw/$tag" "$seed" "$variant" 8 0 \
      > "$OUT/$tag.log" 2>&1 || rc=$?
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
echo "units ok $ok of $want"
