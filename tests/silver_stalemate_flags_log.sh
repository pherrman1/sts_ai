#!/usr/bin/env bash
# STS_SILVER_LOSS_CEILING and STS_SILVER_MAX_BACKUP (research, default off): each logs its research line when on
# (also next to other leaf options), neither logs when unset, and malformed values are refused. Short act4replay
# Shield & Spear -> Heart chain on the price-table identity states, battle seeds 111459990-993 (used smoke block).
# Run from the repo root. usage: silver_stalemate_flags_log.sh ONE_COMBAT
set -euo pipefail
BIN=$1
D=tests/data/silver_price_table_identity
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=${HOME:-/tmp}" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_FAIR=1
   STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0
   STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_LEARNED_STOP=0 STS_ACT4REPLAY_CHAIN=heart)
run() {  # run TAG [ENV...]; returns the run's exit status
  local tag=$1; shift
  env -i "${E[@]}" "$@" bash tools/seed_guard.sh "$BIN" act4replay 4 "$D/states.jsonl" "$T/$tag" 111459990 500 1 \
    > "$T/$tag.log" 2>&1
}
ok() { run "$@" || { cat "$T/$1.log"; echo "FAIL: $1 run"; exit 1; }; }
ok off
! grep -q "loss ceiling\|max backup" "$T/off.log" || { echo "FAIL: off run logs a stalemate flag"; exit 1; }
ok ceil STS_SILVER_LOSS_CEILING=1
grep -q "\[silver\] research leaf: loss ceiling on" "$T/ceil.log" || { echo "FAIL: loss ceiling not logged"; exit 1; }
ok ceilgold STS_SILVER_LOSS_CEILING=1 STS_SILVER_GOLD_WEIGHT=0.5
grep -q "\[silver\] research leaf: loss ceiling on" "$T/ceilgold.log" || { echo "FAIL: loss ceiling not logged with gold"; exit 1; }
ok ceil0 STS_SILVER_LOSS_CEILING=0
! grep -q "loss ceiling" "$T/ceil0.log" || { echo "FAIL: =0 logs the loss ceiling"; exit 1; }
ok maxb STS_SILVER_MAX_BACKUP=4
grep -q "\[silver\] research search: max backup min visits=4" "$T/maxb.log" || { echo "FAIL: max backup not logged"; exit 1; }
for bad in STS_SILVER_LOSS_CEILING=2 STS_SILVER_LOSS_CEILING=true STS_SILVER_MAX_BACKUP=abc STS_SILVER_MAX_BACKUP=4x; do
  if run bad "$bad"; then echo "FAIL: $bad was accepted"; exit 1; fi
done
echo "PASS stalemate flags log and strict parsing"
