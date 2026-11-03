#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of G1 (PREREG.md): CRIT_PRE's final net vs heart1, policy alone.
# Two games per seed, same seed: GH = heart1 (BASE's net-0000 4288d095: heart1.bin with zero-init PPO inputs, policy
# bit-identical to heart1) and GC = CRIT_PRE's net-0060 (1575c27e). Both in PPO mode as trained (STS_OOC_HEART1_PPO=1:
# the net makes every out-of-combat decision, keys included) at temperature 0 (argmax, the eval policy).
# Combat: G0's base B = flat Silver 1,000 (learned stop off, Act 4 strong off, g7f_E root and tree prior, boss prior
# playouts), not the K15 self-play combat. Binary 71cfd280 (build inputs defaa930, the screen's actors' engine).
# Seeds 111520000-111522047 (new), smokes 111529990-111529991 (local, not analysed). Order rotated by seed. Exits 0.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = 71cfd280e121811f ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/critpre.bin" | cut -c1-16)" = 1575c27e92fb35c2 ] || { echo "bad $RUN/critpre.bin" >&2; exit 2; }
[ "$(sha256sum < "$RUN/heart1.bin" | cut -c1-16)" = 4288d0956ab75c3c ] || { echo "bad $RUN/heart1.bin" >&2; exit 2; }
if ! { { [ "$SEED" -ge 111520000 ] && [ "$SEED" -le 111522047 ]; } || [ "$SEED" = 111529990 ] || [ "$SEED" = 111529991 ]; }; then
  echo "seed $SEED outside the frozen block" >&2; exit 2
fi
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364 STS_SILVER_LEARNED_STOP=0
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_MCTS=0 STS_SILVER_ACT4_STRONG=0
  STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8
  STS_OOC_HEART1_PPO=1 STS_OOC_HEART1_TEMPERATURE=0 STS_OOC_HEART1_SAMPLE_SALT=0)
ARMS=(GH GC)
cd "$REPO" || exit 2
for ((i = 0; i < 2; i++)); do
  arm=${ARMS[$(( (i + SEED) % 2 ))]}
  case $arm in GH) net=heart1 ;; GC) net=critpre ;; esac
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}" "STS_OOC_HEART1=$RUN/$net.bin")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 1000 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/$net.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims 1000 " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    grep -q "flat budget" "$b.log" "$b.err" || rc=92
    ! grep -q "tiered sims" "$b.log" "$b.err" || rc=90
    grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" "$b.log" "$b.err" || rc=89
    grep -q "^\[heart1_ppo\] seed=$SEED " "$b.log" "$b.err" || rc=88
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
exit 0
