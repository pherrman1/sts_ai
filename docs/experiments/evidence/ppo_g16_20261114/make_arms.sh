#!/usr/bin/env bash
# usage (on the learner PC, author only, once per store): make_arms.sh run|smoke STORE NET0420
#   run    freezes PG16H24  (arms.txt,       seeds 112100000 + 520*i, sims 16000) in STORE (screen.manifest)
#   smoke  freezes SMOKE  (smoke/arms.txt, seeds 112199990-112199998, sims 1000) in STORE (smoke/screen.manifest)
#   NET0420 LONG_C's net-0420.bin (sha256 8c0bd16c...), checked before init
# DRY=1 prints only.
set -euo pipefail
MODE=$1 STORE=$2 NET=$3
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(git -C "$D" rev-parse --show-toplevel)
case $MODE in
  run)   A=$D/arms.txt       M=$D/screen.manifest       SEED_BASE=112100000 SIMS=16000 ;;
  smoke) A=$D/smoke/arms.txt M=$D/smoke/screen.manifest SEED_BASE=112199990 SIMS=1000 ;;
  *) echo "usage: $0 run|smoke STORE NET0420" >&2; exit 2 ;;
esac
[ "$(awk '$1=="store"{print $2}' "$M")" = "$STORE" ] || { echo "STORE is not $M's store" >&2; exit 2; }
SHA=$(awk '$1=="binary_sha256"{print $2}' "$M")
[ "$(sha256sum "$NET" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "$NET is not net-0420 (8c0bd16c)" >&2; exit 2; }
grep -v '^\s*#' "$A" | while read -r name games iters warm parts init hp; do
  [ -n "$name" ] || continue
  [ "$init" = net-0420 ] || { echo "bad init $init" >&2; exit 2; }
  # shellcheck disable=SC2086
  set -- python3 "$REPO/tools/heart1/ppo_cloud.py" init "$STORE" "$name" --init "$NET" --env-file "$D/actors_frozen.env" \
    --one-combat-sha "$SHA" --iterations "$iters" --games "$games" --parts "$parts" --seed-base "$SEED_BASE" \
    --sims "$SIMS" --asc 20 --value-warmup "$warm" --pipeline 1 -- $hp
  if [ "${DRY:-0}" = 1 ]; then echo "$*"; else "$@"; fi
done
