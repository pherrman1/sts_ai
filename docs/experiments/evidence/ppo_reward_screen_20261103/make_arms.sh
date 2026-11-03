#!/usr/bin/env bash
# usage: make_arms.sh STORE HEART1_NET CRITPRE_NET ONE_COMBAT_SHA
# Freezes one ppo_cloud arm (config + net-0000) per line of arms.txt in STORE (git:URL#PREFIX) (author only, once;
# see PREREG.md). Column "init" picks the start net: heart1 = HEART1_NET, critpre = CRITPRE_NET (heart1 with the
# critic pre-trained by ppo_critic_pretrain.py). The PHI_*_SHA placeholders in arms.txt are replaced by the sha256
# of the committed phi files (the learner re-checks them). Combat = K15, as screen 1 (actors_frozen.env is screen 1's).
# DRY=1 prints the init commands and touches no store.
set -euo pipefail
STORE=$1 HEART1=$2 CRITPRE=$3 SHA=$4
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$D" rev-parse --show-toplevel)
SEED_BASE=111470000
FLOOR_SHA=$(sha256sum "$D/phi_floor.json" | cut -d' ' -f1)
STATE_SHA=$(sha256sum "$D/phi_state.json" | cut -d' ' -f1)
grep -v '^\s*#' "$D/arms.txt" | while read -r name games iters warm parts init hp; do
  [ -n "$name" ] || continue
  case $init in heart1) NET=$HEART1 ;; critpre) NET=$CRITPRE ;; *) echo "bad init $init" >&2; exit 2 ;; esac
  hp=${hp//PHI_FLOOR_SHA/$FLOOR_SHA}; hp=${hp//PHI_STATE_SHA/$STATE_SHA}
  # shellcheck disable=SC2086
  set -- python3 "$REPO/tools/heart1/ppo_cloud.py" init "$STORE" "$name" --init "$NET" --env-file "$D/actors_frozen.env" \
    --one-combat-sha "$SHA" --iterations "$iters" --games "$games" --parts "$parts" --seed-base "$SEED_BASE" \
    --value-warmup "$warm" --pipeline 1 -- $hp
  if [ "${DRY:-0}" = 1 ]; then echo "$*"; else "$@"; fi
done
