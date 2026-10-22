#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT CFG SKIP TAKE -- one slice of the endgame exact study: exact_combat_solver
# roots on the eligible roots SKIP..SKIP+TAKE-1 of one frozen input (A20 elite and boss decisions on the last turns
# of a fight, recorded by `one_combat endgamerootgen` on seeds 111149700-767, filtered and shuffled by
# make_inputs.py). The campaign's build_target is exact_combat_solver; worker.sh stages it as $RUN/one_combat.
# Configs (all with the default horizon collapse "all"; 30 s wall-clock per bound pass, one thread, at most 3 GB of
# address space per solver so that four lanes fit a 15 GB container; a root over it ends as "std::bad_alloc"):
#   S0  lost fights, last three turns: P(survive this turn), exact (one pass)
#   C0  last turn of every fight: win objective (Silver score of a win, 0 for a loss), lower and upper bound
#   S1  lost fights, second-to-last turn: P(survive through the next turn), exact (one pass)
#   C2  won fights, second-to-last turn: win objective, horizon 0, lower bound plays Silver's playout policy 1 turn
#   C1  won fights, second-to-last turn: win objective, horizon 1
# Always exits 0 (rc is in .done).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 CFG=$4 SKIP=$5 TAKE=$6
case $CFG in
  S0) IN=S0 A=(--objective survive --horizon 0 --to-end 0,1,2) ;;
  C0) IN=C0 A=(--objective win --horizon 0 --to-end 0) ;;
  S1) IN=S1 A=(--objective survive --horizon 1 --to-end 1) ;;
  C2) IN=W1 A=(--objective win --horizon 0 --policy-lower 1 --to-end 1) ;;
  C1) IN=W1 A=(--objective win --horizon 1 --to-end 1) ;;
  *) echo "unknown config $CFG" >&2; exit 2 ;;
esac
[[ "$SKIP" =~ ^[0-9]+$ && "$TAKE" =~ ^[1-9][0-9]*$ ]] || { echo "bad slice $SKIP $TAKE" >&2; exit 2; }
[ -s "$RUN/$IN.jsonl" ] || { echo "missing $RUN/$IN.jsonl" >&2; exit 2; }
mkdir -p "$OUT"; base=$OUT/$CFG-$SKIP
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
(ulimit -v 3000000 && exec env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" timeout 3h "$RUN/one_combat" roots \
  "$RUN/$IN.jsonl" "$base.jsonl" "${A[@]}" --time-limit 30 --skip "$SKIP" --take "$TAKE") > "$base.log" 2>&1 || rc=$?
echo "tag=$CFG-$SKIP rc=$rc rows=$(cat "$base.jsonl" 2>/dev/null | wc -l) start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
