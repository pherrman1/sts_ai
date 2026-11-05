#!/usr/bin/env bash
# usage (on the learner PC, author only, once): make_arms.sh STORE LONGB_DIR LOCAL
#   STORE     git:URL#PREFIX of LONG_C (screen.manifest)
#   LONGB_DIR LONG_B's learner directory (~/ppo-longb/LONG_B): config.json, state.pt and loop.json after update 220,
#             net-0219.bin, net-0220.bin
#   LOCAL     the serve LOCAL directory for LONG_C (~/ppo-longb; the arm directory LOCAL/LONG_C must not exist)
# Freezes LONG_C (config + net-0219 + net-0220) in STORE as a continuation of LONG_B (PREREG.md). DRY=1 prints only.
set -euo pipefail
STORE=$1 SRC=$2 LOCAL=$3
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$D" rev-parse --show-toplevel)
SHA=$(awk '$1=="binary_sha256"{print $2}' "$D/screen.manifest")
NET220=408b2982   # LONG_B net-0220 (RESULT.md, eval); checked against the file before init
[ "${DRY:-0}" = 1 ] || [ "$(sha256sum "$SRC/net-0220.bin" | cut -c1-8)" = "$NET220" ] || { echo "net-0220 is not $NET220" >&2; exit 2; }
grep -v '^\s*#' "$D/arms.txt" | while read -r name games iters warm parts init hp; do
  [ -n "$name" ] || continue
  [ "$init" = "continue:LONG_B@220" ] || { echo "bad init $init" >&2; exit 2; }
  # shellcheck disable=SC2086
  set -- python3 "$REPO/tools/heart1/ppo_cloud.py" init "$STORE" "$name" --fork-dir "$SRC" --fork-at 220 --continue \
    --local "$LOCAL" --env-file "$D/actors_frozen.env" --one-combat-sha "$SHA" --iterations "$iters" --games "$games" \
    --parts "$parts" --seed-base 111540000 --value-warmup "$warm" --pipeline 1 -- $hp
  if [ "${DRY:-0}" = 1 ]; then echo "$*"; else "$@"; fi
done
