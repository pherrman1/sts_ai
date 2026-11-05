#!/usr/bin/env bash
# Stage C, price-table leaf at Shield & Spear (../PREREG-stageC.md). usage: run_unit.sh REPO RUN UNIT_OUT I --
# S&S entry state I (0-based line of ss_states.tar's ss.jsonl; 0..591 = §724's Incense states, 592.. = states
# without Incense Burner) played with STS_ACT4REPLAY_CHAIN=heart (S&S, then the Heart from the S&S end state) in
# arms D (default leaf), T (STS_SILVER_PRICE_TABLE_LEAF=a746), TA (a746:anchor) and, for I < 592 only, I
# (STS_SILVER_INCENSE_HEART_PHASE=1) and TI (T + I); 4 replicates each. Replicate r uses battle seed BLOCK[r] + I
# (§724's four used blocks); all arms share every seed. Silver exactly as §724's run_unit.sh. Always exits 0 (rc in
# the .done line); 2 h timeout per run (rc 124).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 I=$4
[[ "$I" =~ ^[0-9]+$ ]] && [ "$I" -lt 1024 ] || { echo "bad state index $I" >&2; exit 2; }
mkdir -p "$OUT/in"
tar -xf "$RUN/ss_states.tar" -C "$OUT/in" || { echo "cannot extract ss_states.tar" >&2; exit 2; }
BLOCKS=(111384000 111382000 111395000 111398100)
E=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STS_COLLECT_KEYS=1 STS_FAIR=1 STS_ACTIVE_POWER_FEATURES=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_REUSE_CAP_MODE=allocated
  STS_ACT4REPLAY_BUDGET=learned STS_ACT4REPLAY_CHAIN=heart STS_SILVER_LEARNED_STOP=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_ACT4_STRONG=0 STS_SILVER_EXACT_ROOT_BUDGETS=0
  STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=0 STS_SILVER_NODE_REUSE_CAP=262144
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8)
cd "$REPO" || exit 2
printf '%s\n' "${E[@]}" | grep '^STS_' > "$OUT/u$I.env"
sed -n "$((I + 1))p" "$OUT/in/ss.jsonl" > "$OUT/s$I.jsonl"
start=$(date -u +%FT%TZ); t0=$(date +%s); rc=0
[ -s "$OUT/s$I.jsonl" ] || rc=96
ARMS=(D T TA); [ "$I" -lt 592 ] && ARMS+=(I TI)
PT="[silver] research leaf: price table a746 at SHIELD_AND_SPEAR"
for arm in "${ARMS[@]}"; do
  case $arm in
    D) A=() ;;
    T) A=(STS_SILVER_PRICE_TABLE_LEAF=a746) ;;
    TA) A=(STS_SILVER_PRICE_TABLE_LEAF=a746:anchor) ;;
    I) A=(STS_SILVER_INCENSE_HEART_PHASE=1) ;;
    TI) A=(STS_SILVER_PRICE_TABLE_LEAF=a746 STS_SILVER_INCENSE_HEART_PHASE=1) ;;
  esac
  for r in 0 1 2 3; do
    [ "$rc" = 96 ] && break 2
    tag="u$I-$arm-r$r"
    env -i "${E[@]}" "${A[@]}" timeout 2h bash tools/seed_guard.sh "$RUN/one_combat" act4replay 1 "$OUT/s$I.jsonl" \
      "$OUT/$tag" "$((BLOCKS[r] + I))" 10000 1 > "$OUT/$tag.log" 2>&1
    x=$?; [ "$x" = 0 ] || { rc=$x; continue; }
    [ "$(grep -c ',learned,' "$OUT/$tag.csv")" = 1 ] || rc=93
    grep -q "learned stop gbt-0cac7cc64364; one-action roots unsearched" "$OUT/$tag.log" || rc=94
    grep -q "research node reuse cap 262144" "$OUT/$tag.log" || rc=95
    case $arm in I|TI) grep -q "incense heart phase scale=1.33 HP/pp" "$OUT/$tag.log" || rc=97 ;;
                 *) ! grep -q "incense heart phase" "$OUT/$tag.log" || rc=97 ;; esac
    case $arm in
      T|TI) grep -qxF "$PT" "$OUT/$tag.log" || rc=98 ;;
      TA) grep -qxF "$PT win bonus anchored" "$OUT/$tag.log" || rc=98 ;;
      *) ! grep -q "research leaf: price table" "$OUT/$tag.log" || rc=98 ;;
    esac
  done
done
rm -rf "$OUT/in"
echo "tag=u$I rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$OUT/u$I.done"
exit 0
