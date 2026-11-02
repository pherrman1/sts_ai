#!/usr/bin/env bash
# usage: make_arms.sh STORE START_NET ONE_COMBAT_SHA COMBAT
# Freezes one ppo_cloud arm (config + net-0000) per line of arms.txt in STORE (git:URL#PREFIX) (author only, once, after G0 and the
# cost arms decided START_NET and COMBAT; see PREREG.md). COMBAT is B, K1, K4, K5 or K15 (ppo_cost_arms_g0_20261101).
# DRY=1 only writes actors_frozen.env (for the launch commit's review) and touches no store.
set -euo pipefail
STORE=$1 NET=$2 SHA=$3 COMBAT=$4
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$D" rev-parse --show-toplevel)
ENV=$(mktemp)
cp "$D/actors_base.env" "$ENV"
prior_off() { sed -i '/^STS_SILVER_ROOT_PRIOR/d; /^STS_SILVER_TREE_PRIOR_MIN_VISITS/d; /^STS_SILVER_ROLLOUT_ROOT_TABLE/d' "$ENV"
              printf '%s\n' STS_SILVER_ROLLOUT_ROOT_TABLE=0 STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0 >> "$ENV"; }
case $COMBAT in
  B) ;;
  K1) echo STS_SIMS_NORMAL=200 >> "$ENV" ;;
  K4) echo STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0 >> "$ENV" ;;
  K5) prior_off ;;
  K15) prior_off; echo STS_SIMS_NORMAL=200 >> "$ENV" ;;
  *) echo "bad COMBAT $COMBAT" >&2; exit 2 ;;
esac
SEED_BASE=111400000
if [ "${DRY:-0}" = 1 ]; then cp "$ENV" "$D/actors_frozen.env"; rm -f "$ENV"; echo "wrote $D/actors_frozen.env"; exit 0; fi
grep -v '^\s*#' "$D/arms.txt" | while read -r name games iters warm parts hp; do
  [ -n "$name" ] || continue
  # shellcheck disable=SC2086
  python3 "$REPO/tools/heart1/ppo_cloud.py" init "$STORE" "$name" --init "$NET" --env-file "$ENV" --one-combat-sha "$SHA" \
    --iterations "$iters" --games "$games" --parts "$parts" --seed-base "$SEED_BASE" --value-warmup "$warm" \
    --pipeline 1 -- $hp
done
cp "$ENV" "$D/actors_frozen.env"   # committed with the launch commit
rm -f "$ENV"
