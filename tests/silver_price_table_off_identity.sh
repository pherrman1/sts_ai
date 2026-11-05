#!/usr/bin/env bash
# STS_SILVER_PRICE_TABLE_LEAF (research, default off): with the option unset or 0, a short act4replay
# Shield & Spear -> Heart chain must give the rows main 4851f703 gave (tests/data/silver_price_table_identity/
# expected.csv, written by that binary; CPU columns dropped). With the option on, the same run must load the model,
# log the research line and give 4 valid rows. Battle seeds 111459990-993 (used smoke block). Run from the repo root.
# usage: silver_price_table_off_identity.sh ONE_COMBAT [--write-expected]
set -euo pipefail
BIN=$1
D=tests/data/silver_price_table_identity
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=${HOME:-/tmp}" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_FAIR=1
   STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0
   STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_LEARNED_STOP=0 STS_ACT4REPLAY_CHAIN=heart)
run() {  # run TAG [ENV...]
  local tag=$1; shift
  env -i "${E[@]}" "$@" bash tools/seed_guard.sh "$BIN" act4replay 4 "$D/states.jsonl" "$T/$tag" 111459990 500 1 \
    > "$T/$tag.log" 2>&1 || { cat "$T/$tag.log"; echo "FAIL: $tag run"; exit 1; }
  cut -d, -f1-14,16-22 "$T/$tag.csv" > "$T/$tag.rows"
}
run off
if [ "${2:-}" = "--write-expected" ]; then cp "$T/off.rows" "$D/expected.csv"; echo "wrote $D/expected.csv"; exit 0; fi
diff "$D/expected.csv" "$T/off.rows" || { echo "FAIL: rows with the option unset differ from main"; exit 1; }
run zero STS_SILVER_PRICE_TABLE_LEAF=0
diff "$D/expected.csv" "$T/zero.rows" || { echo "FAIL: rows with the option =0 differ from main"; exit 1; }
! grep -q "price table" "$T/off.log" "$T/zero.log" || { echo "FAIL: off run logs the price table"; exit 1; }
run on STS_SILVER_PRICE_TABLE_LEAF=a746
grep -q "\[silver\] research leaf: price table a746 at SHIELD_AND_SPEAR" "$T/on.log" || { echo "FAIL: on run lacks its log line"; exit 1; }
[ "$(tail -n +2 "$T/on.rows" | cut -d, -f10 | grep -c '^1$')" = 4 ] || { echo "FAIL: on run rows not all valid"; exit 1; }
echo "PASS price-table leaf off identity (4 states; on run: $(tail -n +2 "$T/on.rows" | cut -d, -f11 | paste -sd' ') S&S wins)"
