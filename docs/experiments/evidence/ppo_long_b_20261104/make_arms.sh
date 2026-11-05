#!/usr/bin/env bash
# usage: make_arms.sh STORE HEART1_NET ONE_COMBAT_SHA
# Freezes the arm of arms.txt (config + net-0000) in STORE (git:URL#PREFIX) (author only, once; see PREREG.md).
# HEART1_NET = heart1.bin (1e92f2a6); init extends it with zero-init inputs as in screens 1-2.
# DRY=1 prints the init command and touches no store.
set -euo pipefail
STORE=$1 HEART1=$2 SHA=$3
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$D" rev-parse --show-toplevel)
SEED_BASE=111540000
grep -v '^\s*#' "$D/arms.txt" | while read -r name games iters warm parts init hp; do
  [ -n "$name" ] || continue
  [ "$init" = heart1 ] || { echo "bad init $init" >&2; exit 2; }
  # shellcheck disable=SC2086
  set -- python3 "$REPO/tools/heart1/ppo_cloud.py" init "$STORE" "$name" --init "$HEART1" --env-file "$D/actors_frozen.env" \
    --one-combat-sha "$SHA" --iterations "$iters" --games "$games" --parts "$parts" --seed-base "$SEED_BASE" \
    --value-warmup "$warm" --pipeline 1 -- $hp
  if [ "${DRY:-0}" = 1 ]; then echo "$*"; else "$@"; fi
done
