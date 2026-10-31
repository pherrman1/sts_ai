#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the cheap-combat proxy check (PREREG.md). The key-rules
# contrast of §691 (R rigid ADR-0041 keys = STS_KEY_*=first, F flexible = policy/policy/mask) with student_sel alone
# out of combat (STS_OOC_MCTS=0: key rules, then student_sel argmax, as the 2026-10-31 rollout-cost R/G arms), under
# three combat strengths:
#   P     production real combat: learned Silver stop (gbt-0cac7cc64364), Act 4 strong, bestbench 10000
#   1000  flat Silver 1,000 sims per decision (learned stop off, Act 4 strong off), bestbench 1000
#   200   flat Silver 200 the same way
# ARMS (default "R1000 F1000 R200 F200"; control units "RP FP") picks the games; order rotated by seed. Always exits 0.
# Binary d74cfded (code db216ff0, = §691's binary); student_sel cf6bf7fb.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = d74cfded889b9440 ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/student_sel.bin" | cut -c1-16)" = cf6bf7fb7c3147dc ] || { echo "bad $RUN/student_sel.bin" >&2; exit 2; }
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8 STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=0 "STS_OOC_HEART1=$RUN/student_sel.bin")
read -r -a ARMS <<< "${ARMS:-R1000 F1000 R200 F200}"
N=${#ARMS[@]}
cd "$REPO" || exit 2
for ((i = 0; i < N; i++)); do
  arm=${ARMS[$(( (i + SEED) % N ))]}
  c=${arm:1}
  case ${arm:0:1} in
    R) X=(STS_KEY_SAPPHIRE=first STS_KEY_RUBY=first STS_KEY_EMERALD=first) ;;
    F) X=(STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask) ;;
    *) echo "bad arm $arm" >&2; exit 2 ;;
  esac
  case $c in
    P) X+=(STS_SILVER_LEARNED_STOP=1); SIMS=10000 ;;
    1000|200) X+=(STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0); SIMS=$c ;;
    *) echo "bad arm $arm" >&2; exit 2 ;;
  esac
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}" "${X[@]}")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" bestbench "$SIMS" 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/student_sel.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims $SIMS " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    case $c in
      P) grep -q "learned stop" "$b.log" "$b.err" || rc=92 ;;
      *) grep -q "flat budget" "$b.log" "$b.err" || rc=92 ;;
    esac
    case ${arm:0:1} in
      R) ! grep -q "heart_key_rules " "$b.log" "$b.err" || rc=91 ;;
      F) grep -q "heart_key_rules sapphire=2 ruby=2 ruby_min_hp=0.600 emerald=1" "$b.log" "$b.err" || rc=91 ;;
    esac
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
exit 0
