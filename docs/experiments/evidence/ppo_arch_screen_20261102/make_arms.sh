#!/usr/bin/env bash
# usage: make_arms.sh STORE SCREEN2_LOCAL SCREEN2_SHA P1_SHA
# Freezes one forked ppo_cloud arm per line of arms.txt (author only, once, on the PC next to screen 2's serve
# directory; PREREG.md "Binding under B"). Each arm = `ppo_cloud.py init --fork-dir SCREEN2_LOCAL/SRC --fork-at N
# --local SCREEN2_LOCAL`: the arm's learner directory (state.pt with the construction applied, net-N, loop.json) is
# written to SCREEN2_LOCAL/ARM, and net-N plus SRC's iteration-N parts go into STORE. Actor env = screen 2's
# actors_frozen.env (init_fork checks it equals the source's, as games, parts, seeds, sims and asc). Column "binary"
# picks the actors' one_combat sha: screen2 = SCREEN2_SHA (71cfd280...), P1 = P1_SHA (defaa930 + the P1 diff).
# DRY=1 prints the init commands and touches nothing.
set -euo pipefail
STORE=$1 LOCAL=$2 S2SHA=$3 P1SHA=$4
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$D" rev-parse --show-toplevel)
ENV_FILE=$REPO/docs/experiments/evidence/ppo_reward_screen_20261103/actors_frozen.env
SEED_BASE=111470000
grep -v '^\s*#' "$D/arms.txt" | while read -r name games iters warm parts init binary hp; do
  [ -n "$name" ] || continue
  src=${init%@*} at=${init#*@}
  [[ "$init" == *@* && "$at" =~ ^[0-9]+$ ]] || { echo "bad init $init" >&2; exit 2; }
  case $binary in screen2) SHA=$S2SHA ;; P1) SHA=$P1SHA ;; *) echo "bad binary $binary" >&2; exit 2 ;; esac
  # shellcheck disable=SC2086
  set -- python3 "$REPO/tools/heart1/ppo_cloud.py" init "$STORE" "$name" --fork-dir "$LOCAL/$src" \
    --fork-at "$((10#$at))" --local "$LOCAL" --env-file "$ENV_FILE" --one-combat-sha "$SHA" --iterations "$iters" \
    --games "$games" --parts "$parts" --seed-base "$SEED_BASE" --value-warmup "$warm" --pipeline 1 -- $hp
  if [ "${DRY:-0}" = 1 ]; then echo "$*"; else "$@"; fi
done
