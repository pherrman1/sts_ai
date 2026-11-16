#!/usr/bin/env bash
# Order dominance round 2 (#1057): one A20 run of §797's seed block under §797's environment plus the dominance ladder
# (record_env.sh). usage: run_unit.sh REPO ONE_COMBAT NET0420 OUT_DIR SEED
# rc 98 = seed outside §797's block 111980000-111980255 (data reuse only; no new seeds).
set -uo pipefail
REPO=$1 BIN=$2 NET=$3 OUT=$4 SEED=$5
[[ "$SEED" =~ ^[0-9]+$ ]] || { echo "bad seed $SEED" >&2; exit 2; }
[ "$(sha256sum < "$NET" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $NET" >&2; exit 2; }
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$D/record_env.sh"
mkdir -p "$OUT"; base=$OUT/natural-$SEED
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
if [ "$SEED" -lt 111980000 ] || [ "$SEED" -gt 111980255 ]; then
  rc=98
else
  env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" "${LADDER_ENV[@]}" "STS_OOC_HEART1=$NET" \
    timeout 10h bash tools/seed_guard.sh "$BIN" silverazgen 1 16000 20 "$base" "$SEED" natural 8 1 \
    > "$base.log" 2>&1 || rc=$?
fi
[ -s "$base.jsonl" ] && gzip -f "$base.jsonl"
if [ "$rc" = 0 ] && ! grep -qF "[heart1] loaded $NET " "$base.log"; then rc=96; fi
echo "tag=natural-$SEED rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
