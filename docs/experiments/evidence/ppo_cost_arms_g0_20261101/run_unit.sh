#!/usr/bin/env bash
# usage: run_unit.sh REPO RUN UNIT_OUT SEED -- one seed of the PPO cost-arm admission (K1-K5) or of G0 (PREREG.md).
# Runner, binary and every flag not named below are X1's (cheap_combat_proxy_20261031/run_unit.sh on main, §739):
# bestbench, student_sel or heart1 alone out of combat (STS_OOC_MCTS=0), key rules R (=first) or F (policy/policy/mask).
# Combat C (base: flat Silver 1,000 = learned stop off, Act 4 strong off, bestbench 1000):
#   B   base (replays X1's F1000; same-container cost reference and a determinism check)
#   K1  STS_SIMS_NORMAL=200 (hallway and event fights 200 sims, elites/bosses 1,000)
#   K4  no boss prior playouts (STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0)
#   K5  no learned Silver prior: no root/tree prior, rollout root table off, no prior playouts (the original's Silver)
#   K15 K1 + K5
# (The learned stop is not a cost arm: it searches its checkpoints to 10k whatever the base budget, ~8x slower.)
# Seeds 111382000-111383023 (X1's, USED): games R/F x K1 K4 K5 K15 plus FB. Seeds 111372000-111374047 (G0): F-keys base combat
# with student_sel (GS) and heart1 (GH). Smokes 111386992 (K layout), 111386993 (G0 layout). Order rotated by seed. Always exits 0.
# Binary d39c2b98 (main 6c96c25, X1's), student_sel cf6bf7fb, heart1.bin 1e92f2a6 (silverbot heart1.pt deaba59d).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 SEED=$4
[ "$(sha256sum < "$RUN/one_combat" | cut -c1-16)" = d39c2b9895fc6070 ] || { echo "bad $RUN/one_combat" >&2; exit 2; }
[ "$(sha256sum < "$RUN/student_sel.bin" | cut -c1-16)" = cf6bf7fb7c3147dc ] || { echo "bad $RUN/student_sel.bin" >&2; exit 2; }
[ "$(sha256sum < "$RUN/heart1.bin" | cut -c1-16)" = 1e92f2a6b2432cc9 ] || { echo "bad $RUN/heart1.bin" >&2; exit 2; }
mkdir -p "$OUT"
COMMON=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" "STS_EXECUTABLE_GIT_SHA=$(git -C "$REPO" rev-parse HEAD)"
  OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
  STS_COLLECT_KEYS=1 STS_FAIR=1 STS_STOP_AFTER_ACT=0 STS_REST_WIN=0
  STS_ACTIVE_POWER_FEATURES=1 STS_REWARDLESS_COMBAT_RNG_FIX=1 STS_HAND_UPGRADE_ALL_FIX=1
  STS_SILVER_SEARCH=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1
  STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364
  STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0
  STS_SILVER_PRIOR_PLAYOUT_ELITE=0
  STS_OOC_HEART1_WING_BOOTS_COUNTER=1
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
  STS_OOC_MCTS=0 STS_SILVER_ACT4_STRONG=0)
PRIOR=(STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g7f_E.txt
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400
  STS_SILVER_TREE_PRIOR_MIN_VISITS=8)
if { [ "$SEED" -ge 111382000 ] && [ "$SEED" -le 111383023 ]; } || [ "$SEED" = 111386992 ]; then
  ARMS=(RK1 FK1 RK4 FK4 RK5 FK5 RK15 FK15 FB)
elif { [ "$SEED" -ge 111372000 ] && [ "$SEED" -le 111374047 ]; } || [ "$SEED" = 111386993 ]; then
  ARMS=(GS GH)
else
  echo "seed $SEED outside the frozen blocks" >&2; exit 2
fi
# Smokes only: SMOKE_ARMS="K5 ..." restricts a smoke seed to those combat settings (R and F of each).
if [ -n "${SMOKE_ARMS:-}" ] && [ "$SEED" -ge 111386992 ]; then
  ARMS=(); for c in $SMOKE_ARMS; do ARMS+=("R$c" "F$c"); done
fi
N=${#ARMS[@]}
cd "$REPO" || exit 2
for ((i = 0; i < N; i++)); do
  arm=${ARMS[$(( (i + SEED) % N ))]}
  net=student_sel
  case $arm in
    R*) X=(STS_KEY_SAPPHIRE=first STS_KEY_RUBY=first STS_KEY_EMERALD=first); c=${arm:1} ;;
    F*) X=(STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask); c=${arm:1} ;;
    GS) X=(STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask); c=B ;;
    GH) X=(STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask); c=B; net=heart1 ;;
    *) echo "bad arm $arm" >&2; exit 2 ;;
  esac
  X+=("STS_OOC_HEART1=$RUN/$net.bin")
  case $c in
    B)  X+=("${PRIOR[@]}" STS_SILVER_LEARNED_STOP=0) ;;
    K1) X+=("${PRIOR[@]}" STS_SILVER_LEARNED_STOP=0 STS_SIMS_NORMAL=200) ;;
    K4) X+=("${PRIOR[@]}" STS_SILVER_LEARNED_STOP=0 STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0) ;;
    K5) X+=(STS_SILVER_LEARNED_STOP=0 STS_SILVER_ROLLOUT_ROOT_TABLE=0 STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0) ;;
    K15) X+=(STS_SILVER_LEARNED_STOP=0 STS_SILVER_ROLLOUT_ROOT_TABLE=0 STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0
             STS_SIMS_NORMAL=200) ;;
    *) echo "bad arm $arm" >&2; exit 2 ;;
  esac
  b=$OUT/$arm-$SEED
  E=("${COMMON[@]}" "${X[@]}")
  printf '%s\n' "${E[@]}" | grep '^STS_' > "$b.env"
  start=$(date -u +%FT%TZ); t0=$(date +%s)
  env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$RUN/one_combat" bestbench 1000 1 20 "$SEED" > "$b.log" 2> "$b.err"
  rc=$?
  if [ "$rc" = 0 ]; then
    grep -qF "[heart1] loaded $RUN/$net.bin " "$b.log" "$b.err" || rc=95
    grep -q "seeds $SEED..$SEED  asc 20  sims 1000 " "$b.log" || rc=94
    grep -q "^BEST  *win%=" "$b.log" || rc=93
    grep -q "flat budget" "$b.log" "$b.err" || rc=92
    case $c in
      K1|K15) grep -q "tiered sims: normal=200 elite=-1 boss=-1" "$b.log" "$b.err" || rc=90 ;;
      *) ! grep -q "tiered sims" "$b.log" "$b.err" || rc=90 ;;
    esac
    case $c in
      K5|K15) ! grep -q "root prior ON" "$b.log" "$b.err" || rc=89 ;;
      *) grep -qF "[research Silver root prior ON: models/combat_policy_mlp_g7f_E.txt weight 400; tree prior K=8]" "$b.log" "$b.err" || rc=89 ;;
    esac
    case ${X[0]} in
      STS_KEY_SAPPHIRE=first) ! grep -q "heart_key_rules " "$b.log" "$b.err" || rc=91 ;;
      *) grep -q "heart_key_rules sapphire=2 ruby=2 ruby_min_hp=0.600 emerald=1" "$b.log" "$b.err" || rc=91 ;;
    esac
  fi
  echo "tag=$arm-$SEED rc=$rc start=$start wall=$(( $(date +%s)-t0 ))" > "$b.done"
done
exit 0
