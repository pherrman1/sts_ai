#!/usr/bin/env bash
# STS_SILVER_RISK_VETO (research, default off): logs its research line when on, nothing when unset or 0, and
# malformed values are refused. Short act4replay Shield & Spear -> Heart chain on the price-table identity states,
# battle seeds 111459990-993 (used smoke block, as silver_stalemate_flags_log.sh).
# Run from the repo root. usage: silver_risk_veto_flag_log.sh ONE_COMBAT
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
! grep -q "risk veto" "$T/off.log" || { echo "FAIL: off run logs the risk veto"; exit 1; }
ok zero STS_SILVER_RISK_VETO=0
! grep -q "risk veto" "$T/zero.log" || { echo "FAIL: =0 logs the risk veto"; exit 1; }
ok on STS_SILVER_RISK_VETO=0.05
grep -q "\[silver\] research search: risk veto delta=0.05 share=0.25 min samples=32" "$T/on.log" \
  || { echo "FAIL: risk veto not logged"; exit 1; }
ok share STS_SILVER_RISK_VETO=0.1,0.5
grep -q "\[silver\] research search: risk veto delta=0.1 share=0.5 min samples=32" "$T/share.log" \
  || { echo "FAIL: risk veto share not logged"; exit 1; }
for bad in STS_SILVER_RISK_VETO=abc STS_SILVER_RISK_VETO=0.05x STS_SILVER_RISK_VETO=2 STS_SILVER_RISK_VETO=-0.1 \
           STS_SILVER_RISK_VETO=0.05, STS_SILVER_RISK_VETO=0.05,1.5 STS_SILVER_RISK_VETO=nan; do
  if run bad "$bad"; then echo "FAIL: $bad was accepted"; exit 1; fi
done
echo "PASS risk veto flag log and strict parsing"
