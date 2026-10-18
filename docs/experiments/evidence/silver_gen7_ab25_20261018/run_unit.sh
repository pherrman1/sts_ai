#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN OUT ARM U -- one A/B unit: states 25U+1..25U+25 of RUN/states.jsonl (the 1,094 held-out
# fold-4 Act-4 states), silverazact4gen at 2.5k, 8 copies, tree prior K=8 weight 400, root bonus off (the gen-7
# self-play config), with prior A = g6_E or B = g7_E. State i of the file uses seed SEED0 + i in both arms (paired).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 ARM=$4 U=$5
PER=25 SEED0=111177100 SEEDMAX=111178199 SIMS=2500 COPIES=8
case $ARM in A) PRIOR=$RUN/g6_E.txt ;; B) PRIOR=$RUN/g7_E.txt ;; *) echo "unknown arm $ARM" >&2; exit 2 ;; esac
[[ "$U" =~ ^[0-9]+$ ]] || { echo "bad unit $U" >&2; exit 2; }
S=$(wc -l < "$RUN/states.jsonl")
(( S == 1094 )) || { echo "expected 1094 states, got $S" >&2; exit 2; }
(( PER * U < S )) || { echo "unit $U out of range" >&2; exit 2; }
n=$(( S - PER * U < PER ? S - PER * U : PER )); seed=$(( SEED0 + PER * U ))
(( seed + n - 1 <= SEEDMAX )) || { echo "seed out of block" >&2; exit 2; }
tag=$ARM-u$U
sed -n "$(( PER * U + 1 )),$(( PER * U + n ))p" "$RUN/states.jsonl" > "$OUT/$tag.states.jsonl"
cd "$REPO" || exit 2
env -i PATH="$PATH" HOME="$HOME" STS_EXECUTABLE_GIT_SHA="$(git rev-parse HEAD)" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
  STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated \
  STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 STS_SILVER_VNET_LEAF_DIRECT=0 \
  STS_SILVER_ROOT_PRIOR="$PRIOR" STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
  timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" silverazact4gen "$n" "$OUT/$tag.states.jsonl" "$SIMS" \
  "$OUT/$tag" "$seed" "$COPIES" 8 0 > "$OUT/$tag.log" 2>&1
rc=$?
(( rc == 0 )) || { echo "silverazact4gen rc=$rc" >&2; exit 1; }
gzip "$OUT/$tag.jsonl" || exit 1
echo "tag=$tag arm=$ARM unit=$U states=$n seed0=$seed prior_sha256=$(sha256sum "$PRIOR" | cut -d' ' -f1)" > "$OUT/$tag.unit.txt"
